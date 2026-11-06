"""Destructive-operation tests use a synthetic guild and immutable Git fixtures only."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import test_skyline_features as fixtures
if fixtures.discord is None:
    raise unittest.SkipTest('Install the optional bot requirements')
from test_skyline_features import discord, challenge, settings, FakeGuild, Identity
from bots.skyline_archive.bot import SkylineBot, CleanupCommands, SkylineCommands
from bots.skyline_archive.cleanup import Cleanup, locked
from bots.skyline_archive.cleanup_ui import CleanupView, CleanupConfirmation
from bots.skyline_archive.core import ArchiveError, archive_files, MANIFEST, git_blob_sha, parse_manifest
from bots.skyline_archive.discord_archive import DiscordArchive
from bots.skyline_archive.github import ArchiveProof, GitHub
from bots.skyline_archive.progress import Progress
from bots.skyline_archive.storage import Store
from bots.skyline_archive.workflows import DiscordPipeline, catalog_entry


class Guild(FakeGuild):
    def __init__(self):
        super().__init__()
        self.deleted=[]
        self.after_delete=None

    def prepare(self,c,kind):
        c.type=kind
        c.category_id=c.category.id if c.category else None
        async def delete(**kwargs):
            if kind==discord.ChannelType.category and any(getattr(x,'category_id',None)==c.id for x in self.channels.values()):
                raise AssertionError('Never delete a nonempty category')
            self.deleted.append(c.id)
            self.channels.pop(c.id)
            for ident in list(c.messages):
                self.channels.pop(ident,None)
            if c.category:
                c.category.text_channels.remove(c)
            if c in self.categories:
                self.categories.remove(c)
            if self.after_delete:
                await self.after_delete(c)
        c.delete=AsyncMock(side_effect=delete)
        return c

    async def create_category(self,name,**kwargs):
        return self.prepare(await super().create_category(name,**kwargs),discord.ChannelType.category)

    async def create_text_channel(self,name,category,**kwargs):
        return self.prepare(await super().create_text_channel(name,category,**kwargs),discord.ChannelType.text)

    async def fetch_channels(self):
        return [x for x in self.channels.values() if hasattr(x,'type')]


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.bot=SkylineBot(settings(self.tmp.name))
        self.guild=Guild()
        self.bot.get_guild=lambda _:self.guild
        self.bot.get_channel=self.guild.get_channel
        self.bot.fetch_channel=self.guild.fetch_channel
        self.client=SimpleNamespace(settings=self.bot.settings,user=Identity(999),get_guild=self.bot.get_guild,
            get_channel=self.guild.get_channel,fetch_channel=self.guild.fetch_channel)
        self.bot.archive=DiscordArchive(self.client,self.bot.store,self.bot.attachments,self.bot.preferences)
        self.hub=await self.guild.create_text_channel('hub',await self.guild.create_category('Hub'))
        self.bot.store.save_settings(dict(archive_hub=self.hub.id,archive_enabled=True))
        self.c=challenge()
        await self.bot.archive.publish([self.c])
        self.q=self.bot.store.rows('SELECT * FROM questions')[0]
        self.channel=self.guild.channels[self.q['channel_id']]
        self.cleanup=Cleanup(self.bot)
        self.proof(self.c)

    async def asyncTearDown(self):
        await self.bot.close()
        self.tmp.cleanup()

    def proof(self,*cs):
        files=archive_files(cs)
        self.remote=ArchiveProof('a'*40,parse_manifest(files[MANIFEST]),{p:git_blob_sha(t) for p,t in files.items()})
        self.cleanup.github.archive_proof=AsyncMock(return_value=self.remote)
        self.cleanup.github.head=AsyncMock(return_value=self.remote.head)

    async def plan(self,scope=None):
        return await self.cleanup.plan(scope or {},self.hub.id)

    def interaction(self,owner=456):
        return SimpleNamespace(guild_id=123,user=Identity(owner),channel_id=self.hub.id,channel=self.hub,
            response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock(),send_modal=AsyncMock(),edit_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),edit_original_response=AsyncMock())

    async def test_preview_is_read_only_and_checks_actual_blob_content(self):
        before={name:self.bot.store.rows('SELECT * FROM '+name) for name in ('mappings','questions','deliveries','discord_cleanup')}
        plan=await self.plan()
        self.assertEqual(len(plan.channels),1)
        self.assertEqual(len(plan.categories),1)
        self.assertEqual(self.guild.deleted,[])
        for name,rows in before.items(): self.assertEqual(rows,self.bot.store.rows('SELECT * FROM '+name))
        path=self.remote.manifest[self.c.key]['files'][0]['path']
        self.remote.blobs[path]='b'*40
        self.assertFalse((await self.plan()).items)
        self.assertIn('missing, changed, or older',(await self.plan()).skipped[0]['reason'])

    async def test_missing_manifest_or_one_question_or_current_content_blocks_channel(self):
        c=replace(self.c,questions=(*self.c.questions,'What is a second value?'),question_ids=('abc','def'))
        await self.bot.archive.publish([c])
        self.assertFalse((await self.plan()).channels)
        self.proof(c)
        self.assertEqual(len((await self.plan()).channels),1)
        updated=replace(c,prompt='Updated shared instructions')
        self.bot.store.upsert_challenge(updated)
        self.assertFalse((await self.plan()).channels)
        self.remote.manifest.clear()
        self.assertFalse((await self.plan()).channels)

    async def test_unrelated_channels_protected_hubs_and_nonempty_categories_are_retained(self):
        other=await self.guild.create_text_channel('human-chat',self.channel.category)
        plan=await self.plan()
        self.assertEqual([i['id'] for i in plan.channels],[self.channel.id])
        self.assertEqual(plan.categories,[])
        self.bot.store.save_settings(dict(notification_channel=self.channel.id))
        self.assertFalse((await self.plan()).channels)
        self.assertIn(other.id,self.guild.channels)

    async def test_wrong_topic_author_marker_and_permissions_block_cleanup(self):
        for attr,value in [('topic','Personal channel')]:
            old=getattr(self.channel,attr); setattr(self.channel,attr,value)
            self.assertFalse((await self.plan()).channels); setattr(self.channel,attr,old)
        self.channel.permissions.manage_channels=False
        self.assertFalse((await self.plan()).channels)
        self.channel.permissions.manage_channels=True
        for m in self.channel.messages.values(): m.author.id=777
        self.assertFalse((await self.plan()).channels)

    async def test_ws_rename_preserves_legacy_post_identity_and_leaderboard_destinations(self):
        self.channel.topic=self.channel.topic.replace('WS challenge ','NCL challenge ',1)
        for message in self.channel.messages.values():
            for embed in message.embeds:
                if embed.footer.text:
                    embed.set_footer(text=embed.footer.text.replace('WS archive ','NCL archive ',1))
        before=self.bot.store.rows('SELECT key,channel_id,message_id,thread_id FROM questions')
        self.assertEqual(len((await self.plan()).channels),1)
        await self.bot.archive.publish([self.c])
        self.assertEqual(before,self.bot.store.rows('SELECT key,channel_id,message_id,thread_id FROM questions'))
        self.bot.store.put('leaderboards',{str(self.channel.id):dict(state='active')})
        self.assertFalse((await self.plan()).channels)

    async def test_shared_legacy_channel_requires_all_events_and_scope(self):
        second=replace(self.c,url=self.c.url[:-24]+'4'*24,event='NCL Fall 2026 Team Game')
        self.bot.store.upsert_challenge(second)
        q=self.bot.store.rows('SELECT * FROM questions WHERE challenge_key=?',(second.key,))[0]
        self.bot.store.link_question(q['key'],self.channel.id,12345,12345)
        self.channel.topic='NCL TRACKER: Password Cracking / easy. Seasons and competitions are identified per challenge.'
        self.bot.store.map('channel','password cracking/easy',self.channel.id)
        self.assertFalse((await self.plan()).channels)
        self.proof(self.c,second)
        self.assertEqual(len((await self.plan()).channels),1)
        self.assertFalse((await self.plan(dict(competition='practice-game'))).channels)

    async def test_delete_only_after_proof_preserves_private_data_and_github(self):
        self.bot.store.verification(self.q['key'],'private answer',456,dict(method='fixture',outcome='Inconclusive',evidence='private'))
        plan=await self.plan()
        removed,failures=await self.cleanup.execute(plan,456)
        self.assertEqual(failures,[])
        self.assertEqual([x['id'] for x in removed],self.guild.deleted)
        self.assertEqual(len(removed),2)
        self.assertIn(self.hub.id,self.guild.channels)
        self.assertIsNotNone(self.bot.store.snapshot(self.c.key))
        q=self.bot.store.question(key=self.q['key'])
        self.assertIsNone(q['channel_id']); self.assertIsNotNone(q['github_path'])
        self.assertEqual(self.bot.store.latest_verification(q['key'])['answer'],'private answer')
        self.assertTrue(self.bot.store.discord_retired(self.c.key))
        self.assertEqual(self.bot.store.rows('SELECT * FROM question_locations'),[])
        self.assertEqual(self.cleanup.github.archive_proof.await_count,2)

    async def test_stale_git_local_data_or_discord_structure_requires_new_confirmation(self):
        plan=await self.plan()
        self.proof(self.c)
        self.cleanup.github.archive_proof.return_value=replace(self.remote,head='b'*40)
        with self.assertRaisesRegex(ArchiveError,'changed after preview'): await self.cleanup.execute(plan,456)
        self.proof(self.c)
        self.channel.name='renamed'
        with self.assertRaisesRegex(ArchiveError,'changed after preview'): await self.cleanup.execute(plan,456)
        self.assertFalse(self.guild.deleted)

    async def test_permission_failure_keeps_channel_and_category_and_can_retry(self):
        self.channel.delete.side_effect=discord.Forbidden(SimpleNamespace(status=403,reason='denied'),{'message':'denied'})
        removed,failures=await self.cleanup.execute(await self.plan(),456)
        self.assertEqual(removed,[])
        self.assertEqual(len(failures),2)
        self.assertTrue(self.bot.store.discord_retired(self.c.key))
        self.assertEqual(self.bot.store.rows('SELECT state FROM discord_cleanup')[0]['state'],'failed')

    async def test_restart_reconciles_uncertain_success_without_retrying_delete(self):
        plan=await self.plan()
        item=plan.channels[0]
        self.bot.store.begin_discord_cleanup(item,plan.head,456)
        await self.channel.delete()
        self.bot.store.close(); self.bot.store=Store(self.tmp.name)
        self.cleanup=Cleanup(self.bot)
        await self.cleanup.recover()
        self.assertEqual(self.guild.deleted,[self.channel.id])
        self.assertEqual(self.bot.store.rows('SELECT state FROM discord_cleanup')[0]['state'],'deleted')
        self.assertIsNone(self.bot.store.question(key=self.q['key'])['thread_id'])
        self.assertTrue(self.bot.store.discord_retired(self.c.key))

    async def test_restart_with_channel_still_present_requires_new_confirmation(self):
        plan=await self.plan()
        self.bot.store.begin_discord_cleanup(plan.channels[0],plan.head,456)
        await self.cleanup.recover()
        self.assertEqual(self.guild.deleted,[])
        self.assertEqual(self.bot.store.rows('SELECT state FROM discord_cleanup')[0]['state'],'failed')

    async def test_new_child_during_delete_prevents_category_delete(self):
        async def change(c):
            if c.type==discord.ChannelType.text:
                await self.guild.create_text_channel('new-human-channel',c.category)
        self.guild.after_delete=change
        removed,failures=await self.cleanup.execute(await self.plan(),456)
        self.assertEqual(len(removed),1)
        self.assertIn('category is not empty',failures[0])

    async def test_git_change_mid_cleanup_stops_remaining_deletions(self):
        plan=await self.plan()
        self.cleanup.github.head.side_effect=[plan.head,'c'*40]
        removed,failures=await self.cleanup.execute(plan,456)
        self.assertEqual(len(removed),1)
        self.assertIn('GitHub changed',failures[0])

    async def test_retirement_survives_scheduled_scan_but_manual_scan_can_rebuild(self):
        await self.cleanup.execute(await self.plan(),456)
        self.bot.scan_options={'scheduled':True}
        ident=self.bot.jobs.create({},False)
        self.bot.jobs.catalog(ident,[catalog_entry(self.c)])
        self.bot.jobs.capture(ident,self.c)
        pipeline=DiscordPipeline(self.bot,ident,True,Progress())
        pipeline.offer(self.c.url); await pipeline.finish()
        self.assertIsNone(self.bot.store.question(key=self.q['key'])['channel_id'])
        await self.bot.archive.publish([self.c])
        self.assertIsNotNone(self.bot.store.question(key=self.q['key'])['channel_id'])
        self.assertFalse(self.bot.store.discord_retired(self.c.key))

    async def test_expired_confirmation_and_wrong_owner_cannot_delete(self):
        plan=await self.plan()
        for owner,age in [(789,0),(456,601)]:
            plan.created=time.monotonic()-age
            with self.assertRaises(ArchiveError): await self.cleanup.execute(plan,owner)
        self.assertFalse(self.guild.deleted)

    async def test_owner_bound_ui_wrong_phrase_cancel_and_double_submit(self):
        view=CleanupView(self.bot,456,await self.plan())
        self.assertIn('not those conversations',view.render())
        self.assertFalse(await view.interaction_check(self.interaction(789)))
        modal=CleanupConfirmation(view)
        await modal.on_submit(self.interaction())
        self.assertFalse(self.guild.deleted)
        await view.children[-1].callback(self.interaction())
        self.assertTrue(view.used)
        modal.confirmation._value=view.plan.phrase
        await modal.on_submit(self.interaction())
        self.assertFalse(self.guild.deleted)
        group=CleanupCommands(self.bot)
        self.assertFalse(await group.interaction_check(self.interaction(789)))
        self.assertTrue(await group.interaction_check(self.interaction()))
        self.assertLessEqual(len(SkylineCommands(self.bot).commands),25)

    async def test_shared_scan_lock_blocks_cleanup_and_scans(self):
        entered=asyncio.Event(); release=asyncio.Event()
        async def work(): entered.set(); await release.wait()
        task=asyncio.create_task(locked(self.bot,'cleanup preview',work))
        await entered.wait()
        with self.assertRaises(ArchiveError): await locked(self.bot,'cleanup deleting',work)
        with self.assertRaises(ArchiveError): self.bot.start_sync(all_events=True)
        release.set(); await task
        self.assertFalse(self.bot.busy())

    async def test_v4_migration_preserves_archive_and_retirement_settings(self):
        old=self.bot.store.rows('SELECT * FROM questions')
        self.bot.store.db.executescript('DROP TABLE discord_cleanup; DROP TABLE discord_retirements; PRAGMA user_version=4;')
        self.bot.store.close(); self.bot.store=Store(self.tmp.name)
        self.assertEqual(old,self.bot.store.rows('SELECT * FROM questions'))
        self.assertTrue((Path(self.tmp.name)/'archive.before-v5.sqlite3').exists())

    async def test_confirmation_executes_once_and_does_not_expand_the_preview(self):
        view=CleanupView(self.bot,456,await self.plan())
        modal=CleanupConfirmation(view)
        modal.confirmation._value=view.plan.phrase
        with patch('bots.skyline_archive.cleanup_ui.Cleanup.execute',new=AsyncMock(return_value=([],[]))) as execute:
            await modal.on_submit(self.interaction())
            await modal.on_submit(self.interaction())
        execute.assert_awaited_once()
        self.assertIs(execute.call_args.args[0],view.plan)
        self.assertEqual(execute.call_args.args[1],456)

    async def test_cancel_during_uncertain_delete_keeps_durable_intent_for_recovery(self):
        real_delete=self.channel.delete.side_effect
        async def interrupted(**kwargs):
            await real_delete(**kwargs)
            raise asyncio.CancelledError()
        self.channel.delete.side_effect=interrupted
        with self.assertRaises(asyncio.CancelledError):
            await self.cleanup.execute(await self.plan(),456)
        self.assertEqual(self.bot.store.rows('SELECT state FROM discord_cleanup')[0]['state'],'pending')
        await self.cleanup.recover()
        self.assertEqual(self.bot.store.rows('SELECT state FROM discord_cleanup')[0]['state'],'deleted')
        self.assertEqual(len(self.guild.deleted),1)

    async def test_unmatched_saved_question_blocks_deletion(self):
        with self.bot.store.db:
            self.bot.store.db.execute('UPDATE questions SET text=? WHERE key=?',('An unexported edit',self.q['key']))
        self.assertFalse((await self.plan()).channels)

    async def test_recreation_can_be_reenabled_by_scope_without_touching_github(self):
        await self.cleanup.execute(await self.plan(),456)
        self.assertEqual(self.cleanup.allow_recreation(dict(competition='team-game')),0)
        self.assertTrue(self.bot.store.discord_retired(self.c.key))
        self.assertEqual(self.cleanup.allow_recreation(dict(competition='practice-game')),1)
        self.assertFalse(self.bot.store.discord_retired(self.c.key))

    async def test_github_network_failure_deletes_nothing(self):
        plan=await self.plan()
        self.cleanup.github.archive_proof.side_effect=ArchiveError('GitHub could not be reached')
        with self.assertRaises(ArchiveError): await self.cleanup.execute(plan,456)
        self.assertFalse(self.guild.deleted)


class ProofTests(unittest.IsolatedAsyncioTestCase):
    async def test_truncated_tree_or_symlink_is_not_backup_proof_and_no_write_requests(self):
        c=challenge(); files=archive_files([c]); manifest=parse_manifest(files[MANIFEST])
        gh=GitHub(SimpleNamespace(repository='example/archive',branch='main'),None)
        gh.head=AsyncMock(return_value='a'*40)
        gh._read_manifest=AsyncMock(return_value=manifest)
        gh.request=AsyncMock(side_effect=[{'tree':{'sha':'b'*40}},{'truncated':True}])
        with self.assertRaises(ArchiveError): await gh.archive_proof()
        tree=[dict(path=p,sha=git_blob_sha(t),type='blob',mode='120000') for p,t in files.items()]
        gh.request=AsyncMock(side_effect=[{'tree':{'sha':'b'*40}},{'tree':tree}])
        proof=await gh.archive_proof()
        self.assertIsNotNone(proof.check(c))
        self.assertTrue(all(call.args[0]=='GET' for call in gh.request.call_args_list))
