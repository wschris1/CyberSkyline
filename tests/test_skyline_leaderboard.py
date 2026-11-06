"""Synthetic standings, persistent schedules and Discord mocks; no live messages."""

import asyncio
from contextlib import asynccontextmanager
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

try:
    import discord
except ModuleNotFoundError:
    raise unittest.SkipTest('Install the optional bot requirements')

from bots.skyline_archive.bot import WSBot, WSCommands, SkylineBot
from bots.skyline_archive.core import ArchiveError, SessionExpired
from bots.skyline_archive.discord_archive import marker, is_marker
from bots.skyline_archive.leaderboard import (Leaderboards, LeaderboardReader, interval_seconds,
    leaderboard_url, snapshot_from, rows_from, report)
from bots.skyline_archive.storage import Store

URL = 'https://cyberskyline.com/world/' + '1'*24 + '/leaderboard'


def row(rank, name, points, ident='', own=False):
    return dict(id=ident, cells=[str(rank), name, str(points), '90.00%', 'a minute ago', '50.00%'], own=own)


def page(rows, rank='Rank: 12 / 120'):
    return dict(title='Synthetic Competition', statuses=[rank], filters=['Overall','All Modules'],
                tables=[dict(headers=['Rank','Handle','Points','Accuracy','Last Correct Submission','Completion'], rows=rows)])


def sample():
    return snapshot_from(page([row(11,'Nearby',510,'n'),row(12,'Our team',500,'us',True),row(13,'Other',490,'o')]),
                         page([row(1,'Leader',1000,'l'),row(2,'Runner up',990,'r')]))


class ParsingTests(unittest.TestCase):
    def test_urls_are_normalized_and_untrusted_destinations_rejected(self):
        self.assertEqual(leaderboard_url(URL.removesuffix('/leaderboard')),URL)
        for url in ('http://cyberskyline.com/world/'+'1'*24, URL+'?token=secret', URL+'#private',
                    URL.replace('cyberskyline.com','cyberskyline.com.attacker.test'),
                    URL.replace('cyberskyline.com','user:password@cyberskyline.com'),
                    URL.replace('cyberskyline.com','localhost'), 'https://cyberskyline.com/hosted_events/example'):
            with self.subTest(url=url), self.assertRaises(ArchiveError): leaderboard_url(url)

    def test_human_intervals_and_boundaries(self):
        for text,expected in [('10',600),('10m',600),('30 minutes',1800),('1H',3600),('1d',86400),('7 days',604800)]:
            self.assertEqual(interval_seconds(text),expected)
        for text in ('0','-1','8d','30s','1.5h','1m30s','infinity','9'*5000):
            with self.assertRaises(ArchiveError): interval_seconds(text)

    def test_own_rank_neighbors_and_points_come_from_source_not_sorting(self):
        data=sample()
        self.assertEqual((data['rank'],data['total'],data['own']['points']),(12,120,500))
        self.assertEqual(data['identity'],'us')
        self.assertEqual([r['rank'] for r in data['nearby']],[11,12,13])
        # Equal points do not imply a tie; use the source's rank.
        data=snapshot_from(page([row(12,'Our team',1000,'us',True)]),page([row(1,'Leader',1000,'l')]))
        self.assertEqual(data['rank'],12)

    def test_unranked_theoretical_position_does_not_borrow_someone_elses_score(self):
        data=snapshot_from(page([row(12,'Someone else',700,'other')],'Unranked (theoretical) Rank: 12 / 120'),
                           page([row(1,'Leader',1000)]))
        self.assertIsNone(data['own'])
        self.assertEqual(data['identity'],'')
        self.assertIn('theoretical',report(data,dict(url=URL,interval=600)).description)

    def test_missing_ambiguous_and_changed_identities_fail_closed(self):
        top=page([row(1,'Leader',1000)])
        for data in (page([]),page([row(12,'One',500),row(12,'Two',500)]),
                     page([row(13,'Our team',500,'us',True)])):
            with self.assertRaises(ArchiveError): snapshot_from(data,top)
        with self.assertRaisesRegex(ArchiveError,'identity changed'):
            snapshot_from(page([row(12,'Our team',500,'new-id',True)]),top,'old-id')
        with self.assertRaisesRegex(ArchiveError,'does not match'):
            snapshot_from(page([row(12,'Other',500,'other',True)]),top,expected_name='Our team')

    def test_loading_malformed_and_partial_top_tables_are_not_fresh_standings(self):
        self.assertEqual(rows_from(page([dict(cells=['No data available'])])),[])
        self.assertEqual(rows_from(page([row('?', 'Invalid', 'NaN')])),[])
        with self.assertRaises(ArchiveError): snapshot_from(page([row(12,'Us',500,'us',True)]),page([row(101,'Other',999)]))
        for status in ('Loading rank', 'Rank: 0 / 120', 'Rank: 121 / 120'):
            with self.assertRaises(ArchiveError):
                snapshot_from(page([row(12,'Us',500,'us',True)],status),page([row(1,'Leader',1000)]))

    def test_report_shows_movement_timestamp_and_escapes_mentions(self):
        old=sample(); new=copy.deepcopy(old)
        new['rank']=10; new['own']['rank']=10; new['own']['points']=600
        new['own']['name']='@everyone **Team**'
        embed=report(new,dict(url=URL,interval=600),old)
        self.assertIn('up 2 places',embed.description)
        self.assertIn('+100',embed.description)
        self.assertNotIn('@everyone',embed.description)
        self.assertIn('\\*\\*Team',embed.description)
        self.assertIsNotNone(embed.timestamp)
        for field in embed.fields: self.assertLessEqual(len(field.value),1024)

    def test_legacy_archive_markers_still_match(self):
        self.assertTrue(marker('key').startswith('WS archive '))
        self.assertTrue(is_marker(marker('key').replace('WS archive','NCL archive'),'key'))
        self.assertFalse(is_marker(marker('other'),'key'))

    def test_new_environment_aliases_preserve_old_defaults_and_take_precedence(self):
        from bots.skyline_archive.settings import Settings
        with tempfile.TemporaryDirectory() as directory:
            env={'SKYLINE_STATE_DIR':directory,'SKYLINE_EVENT_URL':URL.removesuffix('/leaderboard')}
            old=Settings.from_env(env,require_bot=False,require_github=False)
            self.assertEqual(old.state_dir,Path(directory))
            env['WS_EVENT_URL']='https://cyberskyline.com/world/'+'2'*24
            renamed=Settings.from_env(env,require_bot=False,require_github=False)
            self.assertEqual(old.state_dir,renamed.state_dir)
            self.assertEqual(renamed.event_url,env['WS_EVENT_URL'])


class ScheduleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name)
        self.messages=[]
        self.clock_value=100000
        self.channel=Mock(spec=discord.TextChannel)
        self.channel.id=222
        self.channel.guild=SimpleNamespace(id=123,me=SimpleNamespace(id=999))
        self.permissions=SimpleNamespace(view_channel=True,send_messages=True,embed_links=True,read_message_history=True)
        self.channel.permissions_for=Mock(return_value=self.permissions)
        async def history(**kwargs):
            for m in self.messages: yield m
        async def send(*args, **kwargs):
            m=SimpleNamespace(id=100+len(self.messages),embeds=[kwargs['embed']] if 'embed' in kwargs else [],
                              author=SimpleNamespace(id=999))
            self.messages.append(m)
            return m
        self.channel.history=history
        self.channel.send=AsyncMock(side_effect=send)
        self.client=SimpleNamespace(store=self.store,settings=SimpleNamespace(guild_id=123,owners={456}),
            archive=SimpleNamespace(channel=AsyncMock(return_value=self.channel)),user=SimpleNamespace(id=999),
            scan_task=None,scan_phase='idle',session_expired=AsyncMock())
        self.client.busy=lambda:self.client.scan_task is not None and not self.client.scan_task.done()
        self.reader=SimpleNamespace(read=AsyncMock(return_value=sample()))
        self.manager=Leaderboards(self.client,self.reader,lambda:self.clock_value)

    async def asyncTearDown(self):
        if self.client.scan_task and not self.client.scan_task.done():
            self.client.scan_task.cancel()
            await asyncio.gather(self.client.scan_task,return_exceptions=True)
        self.store.close(); self.tmp.cleanup()

    def watch(self):
        return self.manager.configure(self.channel,456,URL,'10m')

    def interaction(self):
        return SimpleNamespace(channel_id=222,guild_id=123,user=SimpleNamespace(id=456),
            response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))

    async def test_one_immediate_report_then_due_time_survives_restart(self):
        self.watch(); await self.manager.tick(); await self.manager.tick()
        self.assertEqual(self.channel.send.await_count,1)
        again=Leaderboards(self.client,self.reader,lambda:self.clock_value)
        await again.tick(); self.assertEqual(self.channel.send.await_count,1)
        self.clock_value+=600
        await again.tick(); self.assertEqual(self.channel.send.await_count,2)
        self.assertEqual(again.watches['222']['identity'],'us')

    async def test_busy_scan_prevents_overlap_and_two_ticks_cannot_duplicate(self):
        self.watch()
        self.client.scan_task=asyncio.create_task(asyncio.sleep(10))
        await self.manager.tick(); self.reader.read.assert_not_awaited()
        self.client.scan_task.cancel(); await asyncio.gather(self.client.scan_task,return_exceptions=True)
        entered=asyncio.Event(); release=asyncio.Event()
        async def read(*args): entered.set(); await release.wait(); return sample()
        self.reader.read.side_effect=read
        first=asyncio.create_task(self.manager.tick()); await entered.wait()
        await self.manager.tick(); self.assertEqual(self.reader.read.await_count,1)
        release.set(); await first
        self.assertEqual(self.channel.send.await_count,1)

    async def test_uncertain_send_recovers_existing_report_after_restart(self):
        watch=self.watch()
        original=self.channel.send.side_effect
        async def lost_response(**kwargs):
            await original(**kwargs)
            raise asyncio.CancelledError()
        self.channel.send.side_effect=lost_response
        with self.assertRaises(asyncio.CancelledError): await self.manager.run(watch)
        self.assertIsNotNone(watch['pending'])
        self.assertEqual(len(self.messages),1)
        self.channel.send.side_effect=original
        restarted=Leaderboards(self.client,self.reader,lambda:self.clock_value)
        await restarted.refresh(restarted.watches['222'])
        self.assertEqual(len(self.messages),1)
        self.assertIsNone(restarted.watches['222']['pending'])
        self.assertEqual(self.reader.read.await_count,1)

    async def test_known_invalid_session_prevents_repeated_reads(self):
        watch=self.watch(); self.store.put('auth_invalid',True)
        await self.manager.tick(); await self.manager.refresh(watch)
        self.reader.read.assert_not_awaited(); self.channel.send.assert_not_awaited()
        self.store.put('auth_invalid',False); await self.manager.tick()
        self.assertEqual(self.reader.read.await_count,1)

    async def test_invalid_session_does_not_block_another_channels_saved_delivery(self):
        first=self.watch()
        pending=copy.deepcopy(first)
        pending.update(channel=333,due=first['due']+1)
        snapshot=sample(); embed=report(snapshot,pending); embed.set_footer(text='WS leaderboard recovery')
        pending['pending']=dict(created=self.clock_value,marker='WS leaderboard recovery',snapshot=snapshot,embed=embed.to_dict())
        self.manager.watches['333']=pending
        self.clock_value+=2
        self.store.put('auth_invalid',True)
        await self.manager.tick()
        self.reader.read.assert_not_awaited()
        self.channel.send.assert_awaited_once()
        self.assertIsNone(pending['pending'])
        self.assertIn('login refresh',first['status'])

    async def test_session_expiration_is_distinct_from_network_failure(self):
        watch=self.watch(); self.reader.read.side_effect=SessionExpired('Refresh login')
        await self.manager.tick()
        self.client.session_expired.assert_awaited_once()
        self.channel.send.assert_not_awaited()
        self.reader.read.side_effect=OSError('private provider response')
        await self.manager.refresh(watch)
        self.assertNotIn('private provider',watch['status'])
        self.assertEqual(watch['errors'],1)

    async def test_failures_do_not_repost_stale_scores_or_spam_notices(self):
        watch=self.watch(); await self.manager.tick()
        previous=copy.deepcopy(watch['previous'])
        self.reader.read.side_effect=ArchiveError('Rankings are hidden')
        # Mock content sends as well as embeds without inspecting private source values.
        self.channel.send=AsyncMock(return_value=SimpleNamespace(id=500))
        await self.manager.refresh(watch); await self.manager.refresh(watch)
        self.assertEqual(self.channel.send.await_count,1)
        self.assertNotIn('embed',self.channel.send.call_args.kwargs)
        self.assertEqual(watch['previous'],previous)

    async def test_stop_and_manual_refresh_preserve_schedule_state(self):
        watch=self.watch(); i=self.interaction()
        await self.manager.command(i,action='stop')
        self.clock_value+=1000; await self.manager.tick()
        self.reader.read.assert_not_awaited()
        await self.manager.command(i,action='now')
        self.reader.read.assert_awaited_once()
        self.assertEqual(watch['state'],'stopped')
        await self.manager.command(i,action='status')
        self.assertIn('stopped',i.response.send_message.call_args.args[0])

    async def test_bad_destination_and_invalid_configuration_do_not_replace_watch(self):
        old=copy.deepcopy(self.watch()); i=self.interaction()
        with self.assertRaises(ArchiveError): await self.manager.command(i,URL,'0')
        self.assertEqual(self.manager.watches['222'],old)
        self.permissions.embed_links=False
        with self.assertRaises(ArchiveError): await self.manager.command(i,URL,'5m')
        self.assertEqual(self.manager.watches['222'],old)
        self.client.settings.owners=set()
        with self.assertRaises(ArchiveError): await self.manager.destination(old)

    async def test_uncertain_busy_history_never_sends_duplicate(self):
        watch=self.watch()
        snapshot=sample(); embed=report(snapshot,watch); embed.set_footer(text='WS leaderboard pending')
        watch['pending']=dict(created=self.clock_value,marker='WS leaderboard pending',snapshot=snapshot,embed=embed.to_dict())
        self.messages=[SimpleNamespace(author=SimpleNamespace(id=999),embeds=[]) for _ in range(1001)]
        with self.assertRaisesRegex(ArchiveError,'uncertain'): await self.manager.deliver(self.channel,watch)
        self.channel.send.assert_not_awaited()

    async def test_owner_checks_and_command_tree_rename(self):
        for _ in range(2):
            group=WSCommands(self.client)
            self.assertEqual(group.name,'ws'); self.assertLessEqual(len(group.commands),25)
            self.assertIsNotNone(group.get_command('leaderboard')); self.assertIsNotNone(group.get_command('sync'))
            for name in ('survey','maintenance','session','cleanup'):
                child=group.get_command(name)
                i=self.interaction(); i.user.id=777
                self.assertFalse(await child.interaction_check(i))
            self.assertEqual([c.name for c in group.get_command('survey').commands],['watch','status','unwatch'])
            self.assertIsNone(group.get_command('watch-survey'))
        self.assertIs(SkylineBot,WSBot)

    async def test_command_configures_channel_and_sends_first_report(self):
        await self.manager.command(self.interaction(),URL,'1h')
        self.assertEqual(self.manager.watches['222']['interval'],3600)
        self.assertEqual(self.channel.send.await_count,1)
        self.assertEqual(self.channel.send.call_args.kwargs['allowed_mentions'].to_dict()['parse'],[])


class ReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_network_guard_and_browser_cleanup(self):
        context=SimpleNamespace(route=AsyncMock())
        tab=SimpleNamespace(count=AsyncMock(return_value=1),click=AsyncMock())
        page_obj=SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=200)),get_by_role=Mock(return_value=tab))
        closed=[]
        @asynccontextmanager
        async def opened():
            try: yield context
            finally: closed.append(True)
        scanner=SimpleNamespace(opened=opened,page=page_obj)
        own=page([row(12,'Our team',500,'us',True)])
        top=page([row(1,'Leader',1000)])
        reader=LeaderboardReader(SimpleNamespace())
        with patch('bots.skyline_archive.leaderboard.Scanner',return_value=scanner), patch.object(reader,'wait',AsyncMock(side_effect=[own,own,top])):
            data=await reader.read(URL)
        self.assertTrue(closed); self.assertEqual(data['identity'],'us')
        guard=context.route.call_args.args[1]
        for url,method,allowed in [(URL,'GET',True),(URL,'POST',False),('http://localhost','GET',False),
                                   ('https://evil.test/','GET',False),('https://builds.cyberskyline.com/app.js','GET',True)]:
            route=SimpleNamespace(request=SimpleNamespace(url=url,method=method),continue_=AsyncMock(),abort=AsyncMock())
            await guard(route)
            self.assertEqual(route.continue_.await_count,int(allowed))
            self.assertEqual(route.abort.await_count,int(not allowed))

    async def test_login_and_foreign_redirect_are_not_standings(self):
        reader=LeaderboardReader(SimpleNamespace())
        for url,error in [('https://cyberskyline.com/login',SessionExpired),('https://example.test/',ArchiveError)]:
            with self.assertRaises(error): await reader.wait(SimpleNamespace(url=url),own=True)

    async def test_password_form_marks_session_expired(self):
        p=SimpleNamespace(url=URL,evaluate=AsyncMock(return_value=dict(login=True)))
        with self.assertRaises(SessionExpired): await LeaderboardReader(SimpleNamespace()).wait(p,own=True)

    async def test_source_reader_waits_for_actual_rank_and_top_rows(self):
        own=page([row(12,'Our team',500,'us',True)])
        p=SimpleNamespace(url=URL,evaluate=AsyncMock(return_value=own))
        self.assertEqual(await LeaderboardReader(SimpleNamespace()).wait(p,own=True),own)
        top=page([row(1,'Leader',1000)])
        p.evaluate.return_value=top
        self.assertEqual(await LeaderboardReader(SimpleNamespace()).wait(p,own=False),top)
