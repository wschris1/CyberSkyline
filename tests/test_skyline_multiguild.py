"""Multi-server registration and archive isolation. No live Discord/API calls."""

import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import test_skyline_features as fixtures
if fixtures.discord is None:
    raise unittest.SkipTest('Install the optional bot requirements')
import discord
from bots.skyline_archive.bot import WSBot, Workspace, owner_check
from bots.skyline_archive.core import ArchiveError
from bots.skyline_archive.settings import Settings
from test_skyline_features import FakeGuild, Identity, challenge


class MultiGuildTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.settings=Settings.from_env(dict(DISCORD_GUILD_ID='123',DISCORD_OWNER_IDS='456',
            SKYLINE_STATE_DIR=self.tmp.name,DISCORD_ARCHIVE_HUB_ID='789',
            DISCORD_NOTIFICATION_CHANNEL_ID='789',SYNC_INTERVAL_MINUTES='10',
            SKYLINE_EVENT_URL='https://cyberskyline.com/world/'+'1'*24,AI_VERIFY_ENABLED='true'),
            require_bot=False,require_github=False)
        self.bot=WSBot(self.settings)
        self.start=patch.object(Workspace,'start_runtime',new_callable=AsyncMock).start()
        self.sync=patch.object(self.bot.tree,'sync',new=AsyncMock(return_value=[SimpleNamespace(name='ws')])).start()
        self.home=FakeGuild()
        self.other=FakeGuild(); self.other.id=124; self.other.counter=2000
        self.bot._connection._guilds={123:self.home,124:self.other}
        self.bot._connection.user=SimpleNamespace(id=999,name='WS')
        self.bot.get_channel=lambda ident: self.home.get_channel(ident) or self.other.get_channel(ident)
        async def fetch_channel(ident):
            found=self.bot.get_channel(ident)
            if found is None:
                raise discord.NotFound(SimpleNamespace(status=404,reason='missing'),dict(message='missing',code=10003))
            return found
        self.bot.fetch_channel=fetch_channel

    async def asyncTearDown(self):
        await self.bot.close()
        patch.stopall()
        self.tmp.cleanup()

    async def join(self):
        await self.bot.on_guild_join(self.other)
        return self.bot.workspaces[124]

    async def test_restart_registers_all_joined_guilds_and_reconnect_does_not_repeat(self):
        await self.bot.on_ready()
        await self.bot.on_ready()
        self.assertEqual([c.kwargs['guild'].id for c in self.sync.await_args_list],[123,124])
        for ident in (123,124):
            group=self.bot.tree.get_command('ws',guild=discord.Object(id=ident))
            self.assertIs(group.client,self.bot.workspaces[ident])
            self.assertIs(group.get_command('status').binding,group)
            self.assertIs(group.get_command('session').client,self.bot.workspaces[ident])
            self.assertLessEqual(len(group.commands),25)
        self.assertEqual(self.bot.tree.get_commands(),[])  # No duplicate global group.

    async def test_join_after_ready_registers_immediately(self):
        child=await self.join()
        self.assertIsNot(child,self.bot)
        self.sync.assert_awaited_once()
        self.assertEqual(self.sync.await_args.kwargs['guild'].id,124)
        self.assertIs(child.gateway,self.bot)

    async def test_one_registration_failure_does_not_block_other_guilds_and_retries(self):
        self.sync.side_effect=[discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),
                                                dict(message='Missing Access',code=50001)),[],[]]
        await self.bot.on_ready()
        self.assertEqual(self.bot.registered_guilds,{124})
        await self.bot.on_ready()
        self.assertEqual(self.bot.registered_guilds,{123,124})
        self.assertEqual(self.sync.await_count,3)

    async def test_new_defaults_do_not_copy_home_destinations_or_schedule(self):
        self.bot.store.save_settings(dict(archive_hub=890,enabled=True,frequency=10))
        child=await self.join()
        prefs=child.preferences.effective()
        self.assertEqual((prefs['archive_hub'],prefs['notification_channel']),(0,0))
        self.assertFalse(prefs['archive_enabled']); self.assertFalse(prefs['enabled'])
        self.assertFalse(prefs['ai_enabled'])
        self.assertEqual(child.settings.auth_file,self.settings.auth_file)
        self.assertEqual(child.settings.owners,self.settings.owners)
        self.assertEqual(child.store.path,Path(self.tmp.name)/'guilds'/'124'/'archive.sqlite3')
        self.assertEqual(self.bot.store.path,Path(self.tmp.name)/'archive.sqlite3')

    async def test_leave_rejoin_restores_settings_mappings_and_discussion_records(self):
        child=await self.join()
        q=child.store.upsert_challenge(challenge())[0]
        child.store.link_question(q['key'],2001,2002,2003)
        child.store.map('category','sample',2000)
        child.store.verification(q['key'],' Case! ',456,dict(method='fixture',outcome='Inconclusive',evidence='No proof.'))
        child.store.save_settings(dict(default_preview=True,frequency=20))
        await self.bot.on_guild_remove(self.other)
        self.assertNotIn(124,self.bot.workspaces)
        self.assertIsNone(self.bot.tree.get_command('ws',guild=discord.Object(id=124)))
        restored=await self.join()
        self.assertTrue(restored.preferences.effective()['default_preview'])
        self.assertEqual(restored.preferences.effective()['frequency'],20)
        self.assertEqual(restored.store.question(thread_id=2003)['message_id'],2002)
        self.assertEqual(restored.store.mapping('category','sample'),2000)
        self.assertEqual(restored.store.latest_verification(q['key'])['answer'],' Case! ')
        self.assertEqual(self.bot.store.rows('SELECT * FROM questions'),[])

    async def test_same_challenge_gets_independent_channels_and_threads_reused_after_rejoin(self):
        child=await self.join()
        c=challenge()
        for workspace in (self.bot,child):
            await workspace.archive.publish([c])
        homeq=self.bot.store.rows('SELECT * FROM questions')[0]
        childq=child.store.rows('SELECT * FROM questions')[0]
        self.assertNotEqual(homeq['thread_id'],childq['thread_id'])
        self.assertEqual(homeq['key'],childq['key'])
        discussion=await self.other.get_channel(childq['thread_id']).send('Keep this discussion')
        counts=(self.home.counter,self.other.counter)
        await self.bot.on_guild_remove(self.other)
        restored=await self.join()
        await restored.archive.publish([c])
        await self.bot.archive.publish([c])
        self.assertEqual((self.home.counter,self.other.counter),counts)
        self.assertIn(discussion.id,self.other.get_channel(childq['thread_id']).messages)
        self.assertEqual(restored.store.search('example',{},[homeq['channel_id']]),[])
        with self.assertRaisesRegex(ArchiveError,'another server'):
            await restored.archive.channel(homeq['channel_id'])

    async def test_authorization_stays_owner_only_and_bound_to_selected_guild(self):
        child=await self.join()
        for guild,user,expected in ((124,456,True),(124,789,False),(123,456,False)):
            interaction=SimpleNamespace(guild_id=guild,user=Identity(user),
                response=SimpleNamespace(send_message=AsyncMock()))
            self.assertEqual(await owner_check(child,interaction),expected)

    async def test_shared_authentication_latch_and_ai_budget_only(self):
        child=await self.join()
        destination=SimpleNamespace(send=AsyncMock())
        with patch.object(child.archive,'channel',new=AsyncMock(return_value=destination)),\
             patch.object(self.bot.archive,'channel',new=AsyncMock(return_value=destination)):
            await child.session_expired('expired',42)
            await self.bot.session_expired('expired',42)
        destination.send.assert_awaited_once()
        self.assertTrue(self.bot.store.get('auth_invalid'))
        child.store.put('auth_invalid',False)
        self.assertFalse(self.bot.store.get('auth_invalid'))
        child.store.put('openai-requests/2026-11-06',3)
        self.assertEqual(self.bot.store.get('openai-requests/2026-11-06'),3)
        child.store.put('schedule_hold',True)
        self.assertFalse(self.bot.store.get('schedule_hold',False))
        child.store.put('auth_invalid',True,'settings')
        self.assertIsNone(self.bot.store.get('auth_invalid',None,'settings'))
        self.assertIs(child.verifier.lock,self.bot.verifier.lock)

    async def test_shared_job_limit_and_stop_cannot_cancel_another_servers_scan(self):
        child=await self.join()
        self.bot.scan_task=asyncio.create_task(asyncio.Event().wait())
        self.bot.scan_phase='scanning'
        self.assertTrue(child.busy()); self.assertFalse(child.local_busy())
        with self.assertRaisesRegex(ArchiveError,'already running'):
            child.start_sync(preview=True)
        self.assertIn('No scan is running',child.stop_sync())
        child.pause_sync()
        self.assertFalse(self.bot.scan_task.cancelling())
        self.assertFalse(self.bot.store.get('schedule_hold',False))
        self.assertTrue(child.store.get('schedule_hold',False))
        raced=asyncio.create_task(asyncio.Event().wait())
        with self.assertRaisesRegex(ArchiveError,'another WS server'):
            child.scan_task=raced
        await asyncio.gather(raced,return_exceptions=True)
        self.assertTrue(raced.cancelled())
        self.assertIsNone(child.scan_task)

    async def test_preview_new_server_never_changes_home_archive(self):
        child=await self.join()
        from bots.skyline_archive.scanner import ScanResult
        with patch('bots.skyline_archive.bot.Scanner') as scanner,\
             patch.object(child.archive,'publish',new_callable=AsyncMock) as publish:
            scanner.return_value.collect=AsyncMock(return_value=ScanResult(challenges=[challenge()]))
            child.start_sync(all_events=True,preview=True)
            await child.scan_task
            publish.assert_not_awaited()
        self.assertEqual(self.bot.store.rows('SELECT * FROM scans'),[])
        self.assertEqual(child.store.rows('SELECT * FROM questions'),[])
        self.assertEqual(self.home.channels,{})
        self.assertEqual(self.other.channels,{})

    async def test_runtime_starts_once_and_closes_all_workspaces(self):
        child=await self.join()
        patch.stopall()  # Exercise real lifecycle with only the gateway wait mocked.
        with patch.object(self.bot,'wait_until_ready',new=AsyncMock(side_effect=asyncio.Event().wait)),\
             patch('bots.skyline_archive.bot.aiohttp.ClientSession') as session:
            session.return_value.close=AsyncMock()
            await child.start_runtime()
            await child.start_runtime()
            session.assert_called_once()
            tasks=list(child.background)
            await self.bot.close()
            self.assertTrue(child.ws_closing)
            self.assertTrue(all(t.done() for t in tasks))
            session.return_value.close.assert_awaited_once()
        await self.bot.close()  # Idempotent, including shared store shutdown order.


class GuildSettingsTests(unittest.TestCase):
    def test_invalid_guild_id_is_not_a_filesystem_path(self):
        config=Settings.from_env({},require_bot=False,require_github=False)
        for value in ('../other',0,True,-1,2**64):
            with self.assertRaises(ArchiveError): config.for_guild(value)
