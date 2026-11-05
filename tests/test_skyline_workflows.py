"""Split workflow integration tests; all Discord/source/GitHub operations are synthetic."""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import test_skyline_features as fixtures
if fixtures.discord is None:
    raise unittest.SkipTest('Install the optional bot requirements')
from test_skyline_features import challenge, settings, FakeGuild, Identity
from bots.skyline_archive.bot import SkylineBot, SkylineCommands
from bots.skyline_archive.core import ArchiveError, SessionExpired
from bots.skyline_archive.discord_archive import DiscordArchive
from bots.skyline_archive.jobs import Jobs
from bots.skyline_archive.scanner import ScanResult
from bots.skyline_archive.storage import Store
from bots.skyline_archive.workflows import catalog_entry, github_target


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.bot=SkylineBot(settings(self.tmp.name))
        self.guild=FakeGuild()
        self.hub=await self.guild.create_text_channel('hub',await self.guild.create_category('Hub'))
        self.client=SimpleNamespace(settings=self.bot.settings,user=Identity(999),get_guild=lambda _:self.guild,
            get_channel=self.guild.get_channel,fetch_channel=self.guild.fetch_channel)
        self.bot.archive=DiscordArchive(self.client,self.bot.store,self.bot.attachments,self.bot.preferences)
        self.bot.store.save_settings(dict(archive_hub=self.hub.id,archive_enabled=True))
        self.source=patch('bots.skyline_archive.bot.Scanner').start()
        self.remote=patch('bots.skyline_archive.bot.GitHub').start()
        self.remote.return_value.publish=AsyncMock(return_value=SimpleNamespace(changed=0,commit_url=None,manifest={}))

    async def asyncTearDown(self):
        await self.bot.close()
        patch.stopall()
        self.tmp.cleanup()

    def interaction(self):
        return SimpleNamespace(guild_id=123,guild=self.guild,channel=self.hub,channel_id=self.hub.id,user=Identity(456),
            response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock(),is_done=lambda:False),
            followup=SimpleNamespace(send=AsyncMock()))

    def collect(self,*items):
        async def work(*args,**kw):
            await kw['on_catalog']([catalog_entry(c) for c in items],True)
            for c in items:
                await kw['on_challenge'](c,None)
            return ScanResult(challenges=list(items))
        self.source.return_value.collect=AsyncMock(side_effect=work)

    async def run_job(self,workflow,**options):
        self.bot.start_sync(all_events=True,channel=self.hub,workflow=workflow,**options)
        await self.bot.scan_task

    async def test_discord_posts_while_collection_is_still_running_and_never_calls_github(self):
        first=challenge(); second=replace(first,url=first.url[:-24]+'4'*24)
        posting=asyncio.Event(); source_still_running=asyncio.Event()
        real=self.bot.archive.publish
        async def publish(items,progress):
            await real(items,progress)
            posting.set()
        async def collect(*args,**kw):
            await kw['on_catalog']([catalog_entry(first),catalog_entry(second)],True)
            await kw['on_challenge'](first,None)
            await asyncio.wait_for(posting.wait(),1)
            self.assertTrue(self.bot.progress.collecting)
            self.assertEqual(len(self.bot.store.rows('SELECT * FROM questions WHERE thread_id IS NOT NULL')),1)
            source_still_running.set()
            await kw['on_challenge'](second,None)
            return ScanResult(challenges=[first,second])
        self.source.return_value.collect=AsyncMock(side_effect=collect)
        with patch.object(self.bot.archive,'publish',side_effect=publish):
            await self.run_job('discord')
        self.assertTrue(source_still_running.is_set())
        self.assertEqual(self.bot.progress.discord_completed,2)
        self.remote.assert_not_called()
        self.assertTrue(self.bot.store.delivered(first,'discord'))
        self.assertFalse(self.bot.store.delivered(first,github_target(self.bot.settings)))

    async def test_combined_finishes_discord_before_github_and_keeps_it_on_github_failure(self):
        c=challenge(); self.collect(c)
        async def fail(items):
            self.assertEqual(len(self.bot.store.rows('SELECT thread_id FROM questions WHERE thread_id IS NOT NULL')),1)
            self.assertTrue(self.bot.store.delivered(c,'discord'))
            raise ArchiveError('GitHub denied access')
        self.remote.return_value.publish.side_effect=fail
        await self.run_job('both')
        self.assertEqual(self.bot.progress.state,'completed with errors')
        self.assertFalse(self.bot.store.delivered(c,github_target(self.bot.settings)))
        self.assertIn('GitHub export failed',self.bot.jobs.failures()[1][0]['error'])
        old=self.bot.store.rows('SELECT thread_id FROM questions')
        self.remote.return_value.publish.side_effect=None
        self.collect()
        await self.bot.resume_interaction(self.interaction(),retry=True)
        await self.bot.scan_task
        self.assertEqual(old,self.bot.store.rows('SELECT thread_id FROM questions'))
        self.assertTrue(self.bot.store.delivered(c,github_target(self.bot.settings)))

    async def test_export_uses_mapped_source_prompts_even_with_invalid_session_and_private_discussion(self):
        c=challenge(); await self.bot.archive.publish([c])
        q=self.bot.store.rows('SELECT * FROM questions')[0]
        await self.guild.channels[q['thread_id']].send('PRIVATE ANSWER DO NOT EXPORT')
        self.bot.store.verification(q['key'],'PRIVATE ANSWER',456,dict(method='fixture',outcome='Inconclusive',evidence='private'))
        parent=self.guild.channels[q['channel_id']].messages[q['message_id']]
        parent.embeds[0].description+='\nPRIVATE MANUAL ADDITION'
        self.bot.store.put('auth_invalid',True)
        with patch.object(self.guild.channels[q['thread_id']],'history',side_effect=AssertionError('Do not read discussions')):
            await self.run_job('github')
        self.source.assert_not_called()
        self.remote.return_value.publish.assert_awaited_once_with([c])
        self.assertEqual(self.bot.progress.state,'completed')
        self.assertTrue(self.bot.store.delivered(c,github_target(self.bot.settings)))
        self.assertTrue(self.bot.store.get('auth_invalid'))

    async def test_source_preview_has_no_archive_files_or_delivery_markers_for_either_workflow(self):
        for mode in ('discord','both'):
            self.collect(challenge())
            await self.run_job(mode,preview=True)
            for table in ('challenges','posts','mappings','questions','attachments','deliveries'):
                self.assertEqual(self.bot.store.rows('SELECT * FROM '+table),[])
        self.remote.assert_not_called()

    async def test_export_preview_reads_only_and_does_not_mark_github_success(self):
        c=challenge(); await self.bot.archive.publish([c])
        before=self.guild.counter
        await self.run_job('github',preview=True)
        self.assertEqual(before+1,self.guild.counter)  # One allowed progress message.
        self.assertFalse(self.bot.store.delivered(c,github_target(self.bot.settings)))
        self.remote.assert_not_called(); self.source.assert_not_called()
        self.assertIn('No source scan',self.bot.progress.detail)

    async def test_export_filters_and_ignores_unposted_snapshots(self):
        a=challenge(); b=replace(a,url=a.url[:-24]+'4'*24,category='Forensics')
        unposted=replace(a,url=a.url[:-24]+'5'*24)
        await self.bot.archive.publish([a,b]); self.bot.store.upsert_challenge(unposted)
        channel=self.bot.store.question(key=self.bot.store.rows('SELECT key FROM questions WHERE challenge_key=?',(b.key,))[0]['key'])['channel_id']
        await self.run_job('github',archive_channel_id=channel,scope={'category':'forensics','season':'spring-2026'})
        self.remote.return_value.publish.assert_awaited_once_with([b])

    async def test_missing_parent_is_reported_without_reading_chat_or_exporting_it(self):
        c=challenge(); await self.bot.archive.publish([c])
        q=self.bot.store.rows('SELECT * FROM questions')[0]
        del self.guild.channels[q['channel_id']].messages[q['message_id']]
        await self.run_job('github')
        self.remote.assert_not_called()
        self.assertEqual(self.bot.progress.state,'failed')
        self.assertIn('missing',self.bot.jobs.failures()[1][0]['error'])

    async def test_export_rejects_unmanaged_or_spoofed_parent(self):
        c=challenge(); await self.bot.archive.publish([c])
        q=self.bot.store.rows('SELECT * FROM questions')[0]
        self.guild.channels[q['channel_id']].messages[q['message_id']].author=Identity(456)
        await self.run_job('github')
        self.remote.assert_not_called()
        self.assertIn('managed bot archive',self.bot.jobs.failures()[1][0]['error'])

    async def test_export_does_not_export_newer_snapshot_before_its_discord_posts_finish(self):
        c=challenge(); await self.bot.archive.publish([c])
        self.bot.store.upsert_challenge(replace(c,questions=('Changed source question?',)))
        await self.run_job('github')
        self.remote.assert_not_called()
        self.assertIn('has not finished archiving',self.bot.jobs.failures()[1][0]['error'])

    async def test_stop_keeps_posted_questions_and_resume_remembers_discord_only(self):
        c=challenge(); next_c=replace(c,url=c.url[:-24]+'4'*24)
        posted=asyncio.Event(); real=self.bot.archive.publish
        async def publish(items,p):
            await real(items,p); posted.set()
        async def collecting(*args,**kw):
            await kw['on_catalog']([catalog_entry(c),catalog_entry(next_c)],True)
            await kw['on_challenge'](c,None)
            await asyncio.Event().wait()
        self.source.return_value.collect=AsyncMock(side_effect=collecting)
        with patch.object(self.bot.archive,'publish',side_effect=publish):
            self.bot.start_sync(all_events=True,workflow='discord',channel=self.hub)
            await asyncio.wait_for(posted.wait(),1)
            before=self.bot.store.rows('SELECT thread_id FROM questions')
            self.bot.stop_sync()
            await asyncio.gather(self.bot.scan_task,return_exceptions=True)
        self.bot.store.close(); self.bot.store=Store(self.tmp.name); self.bot.jobs=Jobs(self.bot.store)
        self.bot.archive.store=self.bot.store; self.bot.attachments.store=self.bot.store; self.bot.preferences.store=self.bot.store
        self.collect(next_c)
        await self.bot.resume_interaction(self.interaction()); await self.bot.scan_task
        self.assertEqual(json.loads(self.bot.jobs.get(1)['options'])['workflow'],'discord')
        self.assertEqual(before[0]['thread_id'],self.bot.store.rows('SELECT thread_id FROM questions')[0]['thread_id'])
        self.assertEqual(len(self.bot.jobs.items(1,'published')),2)
        self.remote.assert_not_called()

    async def test_workflows_share_one_job_lock(self):
        self.source.return_value.collect=AsyncMock(side_effect=lambda *a,**kw:asyncio.Event().wait())
        self.bot.start_sync(all_events=True,workflow='discord',channel=self.hub)
        for mode in ('discord','both','github'):
            with self.assertRaisesRegex(ArchiveError,'already running'):
                self.bot.start_sync(workflow=mode)
        self.bot.stop_sync()
        await asyncio.gather(self.bot.scan_task,return_exceptions=True)

    async def test_session_expiration_during_stream_keeps_published_content(self):
        c=challenge(); posted=asyncio.Event(); real=self.bot.archive.publish
        async def publish(items,p):
            await real(items,p); posted.set()
        async def collect(*args,**kw):
            await kw['on_catalog']([catalog_entry(c)],True)
            await kw['on_challenge'](c,None)
            await asyncio.wait_for(posted.wait(),1)
            raise SessionExpired('Refresh login')
        self.source.return_value.collect=AsyncMock(side_effect=collect)
        with patch.object(self.bot.archive,'publish',side_effect=publish):
            await self.run_job('both')
        self.assertTrue(self.bot.store.get('auth_invalid'))
        self.assertEqual(self.bot.progress.state,'waiting for login')
        self.assertIsNotNone(self.bot.store.rows('SELECT thread_id FROM questions')[0]['thread_id'])
        self.remote.assert_not_called()

    async def test_commands_remain_owner_only_and_fit_discord_limits(self):
        group=SkylineCommands(self.bot)
        self.assertLessEqual(len(group.commands),25)
        i=self.interaction(); i.user=Identity(789)
        self.assertFalse(await group.interaction_check(i))
        i.user=Identity(456)
        self.assertTrue(await group.interaction_check(i))
        with patch.object(self.bot,'launch_interaction',new=AsyncMock()) as launch:
            for command,mode in (('scan-discord','discord'),('scan-both','both')):
                await group.get_command(command).callback(group,i,all_events=True)
                self.assertEqual(launch.call_args.kwargs['workflow'],mode)
            await group.get_command('export-github').callback(group,i,preview=True)
            self.assertEqual(launch.call_args.kwargs['workflow'],'github')
            with self.assertRaises(ArchiveError):
                await group.get_command('scan-discord').callback(group,i,event_url='https://cyberskyline.com/world/'+'1'*24,all_events=True)

    async def test_v3_migration_preserves_archive_without_inventing_destination_success(self):
        c=challenge(); await self.bot.archive.publish([c])
        before=self.bot.store.rows('SELECT * FROM questions')
        self.bot.store.db.executescript('DROP TABLE deliveries; PRAGMA user_version=3;')
        self.bot.store.close(); self.bot.store=Store(self.tmp.name)
        self.assertEqual(before,self.bot.store.rows('SELECT * FROM questions'))
        self.assertEqual(self.bot.store.rows('SELECT * FROM deliveries'),[])
        self.assertTrue((Path(self.tmp.name)/f'archive.before-v{Store.VERSION}.sqlite3').exists())
        self.assertIsNotNone(self.bot.store.snapshot(c.key))

    async def test_new_parent_avoids_extra_edit_but_repaired_parent_links_surviving_thread(self):
        c=challenge(); await self.bot.archive.publish([c])
        q=self.bot.store.rows('SELECT * FROM questions')[0]
        channel=self.guild.channels[q['channel_id']]
        self.assertEqual(channel.messages[q['message_id']].edits,0)
        self.assertIn(q['thread_id'],self.guild.channels)
        del channel.messages[q['message_id']]
        await self.bot.archive.publish([c])
        repaired=self.bot.store.rows('SELECT * FROM questions')[0]
        self.assertNotEqual(repaired['message_id'],q['message_id'])
        self.assertEqual(repaired['thread_id'],q['thread_id'])
        parent=channel.messages[repaired['message_id']]
        self.assertTrue(any(str(q['thread_id']) in f.value for f in parent.embeds[0].fields if f.name=='Discussion'))
