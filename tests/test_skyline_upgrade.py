"""Upgrade regressions with synthetic state, Discord fakes and mocked network APIs."""

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from test_skyline_features import challenge, settings, FakeGuild, Identity
import test_skyline_features as fixtures
from test_skyline_ai import final_response, tool_response
from bots.skyline_archive.ai_verification import OpenAIAssistant
from bots.skyline_archive.attachments import Attachments
from bots.skyline_archive.bot import SkylineBot, SkylineCommands
from bots.skyline_archive.core import ArchiveError, SessionExpired
from bots.skyline_archive.discord_archive import DiscordArchive
from bots.skyline_archive.jobs import Jobs
from bots.skyline_archive.operations import assistance, evidence, health, reorganize
from bots.skyline_archive.progress import Progress
from bots.skyline_archive.scanner import ScanResult, Scanner
from bots.skyline_archive.storage import Store
from bots.skyline_archive.verify_worker import inspect_evidence, check


def entry(c):
    return dict(url=c.url,event=c.event,event_url='https://cyberskyline.com/world/'+c.ids[0],
                season='spring-2026',competition='practice-game',category=c.category,title=c.title,level='easy')


class UpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.bot=SkylineBot(settings(self.tmp.name))
        self.guild=FakeGuild()
        self.hub=await self.guild.create_text_channel('hub',await self.guild.create_category('Hub'))
        self.client=SimpleNamespace(settings=self.bot.settings,user=Identity(999),get_guild=lambda _:self.guild,
            get_channel=self.guild.get_channel,fetch_channel=self.guild.fetch_channel)
        self.bot.archive=DiscordArchive(self.client,self.bot.store,self.bot.attachments,self.bot.preferences)
        self.bot.store.save_settings(dict(archive_hub=self.hub.id,archive_enabled=True))

    async def asyncTearDown(self):
        await self.bot.close(); self.tmp.cleanup()

    def interaction(self,channel=None):
        channel=channel or self.hub
        return SimpleNamespace(guild_id=123,guild=self.guild,channel=channel,channel_id=channel.id,user=Identity(456),
            response=SimpleNamespace(defer=AsyncMock(),send_message=AsyncMock(),is_done=lambda:False),
            followup=SimpleNamespace(send=AsyncMock()))

    async def question(self,c=None):
        c=c or challenge()
        await self.bot.archive.publish([c])
        q=self.bot.store.question(key=self.bot.store.rows('SELECT key FROM questions WHERE challenge_key=?',(c.key,))[0]['key'])
        return q,self.interaction(self.guild.channels[q['thread_id']])

    async def test_each_challenge_gets_channel_and_each_question_gets_thread(self):
        first=challenge(title='Meta (Easy)',questions=('First?','Second?'),question_ids=('a','b'))
        second=replace(challenge(),url=challenge().url[:-24]+'4'*24,title='Lookup (Easy)')
        await self.bot.archive.publish([first,second])
        qs=self.bot.store.rows('SELECT * FROM questions')
        self.assertEqual(len({q['channel_id'] for q in qs}),2)
        self.assertEqual(len({q['thread_id'] for q in qs}),3)
        self.assertEqual({self.guild.channels[q['channel_id']].name for q in qs},{'meta-easy','lookup-easy'})
        ids=[q['thread_id'] for q in qs]
        await self.bot.archive.publish([first,second])
        self.assertEqual(ids,[q['thread_id'] for q in self.bot.store.rows('SELECT * FROM questions')])

    async def test_same_named_challenges_from_different_events_never_merge(self):
        c=challenge()
        other=replace(c,url=c.url.replace('1'*24,'4'*24),event='NCL Fall 2026 Team Game')
        await self.bot.archive.publish([c,other])
        qs=self.bot.store.rows('SELECT * FROM questions')
        self.assertNotEqual(qs[0]['channel_id'],qs[1]['channel_id'])
        self.assertNotEqual(self.guild.channels[qs[0]['channel_id']].name,self.guild.channels[qs[1]['channel_id']].name)

    async def test_channel_create_recovery_uses_source_identity_topic(self):
        c=challenge(); channel=await self.bot.archive.destination(c)
        with self.bot.store.db:
            self.bot.store.db.execute("DELETE FROM mappings WHERE kind='challenge-channel'")
        self.assertEqual((await self.bot.archive.destination(c)).id,channel.id)

    async def test_v2_migration_preserves_old_discussion_and_verification(self):
        c=challenge(); q=self.bot.store.upsert_challenge(c)[0]
        old=await self.guild.create_text_channel('passcracking-easy',await self.guild.create_category('Old'))
        parent=await old.send('Original question')
        thread=await parent.create_thread(name='Original Q1')
        discussion=await thread.send('My old answer and discussion')
        self.bot.store.link_question(q['key'],old.id,parent.id,thread.id)
        self.bot.store.verification(q['key'],' exact answer ',456,dict(outcome='Inconclusive',method='fixture',evidence='original'))
        await self.bot.archive.publish([c])
        current=self.bot.store.question(key=q['key'])
        self.assertNotEqual(current['thread_id'],thread.id)
        self.assertIn(discussion.id,thread.messages)
        self.assertEqual(self.bot.store.question(thread_id=thread.id)['key'],q['key'])
        intro=''.join(m.embeds[0].description for m in self.guild.channels[current['thread_id']].messages.values())
        self.assertIn(str(thread.id),intro)
        self.assertEqual(self.bot.store.latest_verification(q['key'])['answer'],' exact answer ')
        before=self.guild.counter
        await self.bot.archive.publish([c])
        self.assertEqual(before,self.guild.counter)

    async def test_reorganize_preview_does_not_create_channels(self):
        c=challenge(); self.bot.store.upsert_challenge(c)
        before=self.guild.counter
        await reorganize(self.bot,self.interaction(),True)
        self.assertEqual(before,self.guild.counter)

    async def test_partial_pages_publish_complete_challenge_and_retry_only_failure(self):
        good=challenge(); bad=replace(good,url=good.url[:-24]+'4'*24,title='Other (Easy)')
        async def collect(*args,**kw):
            await kw['on_catalog']([entry(good),entry(bad)],True)
            await kw['on_challenge'](good,None)
            await kw['on_error'](entry(bad),'Unsupported question layout')
            return ScanResult(challenges=[good],errors=['Other: unsupported layout'])
        publication=SimpleNamespace(changed=2,commit_url=None,manifest={})
        with patch('bots.skyline_archive.bot.Scanner') as scanner,patch('bots.skyline_archive.bot.GitHub') as github:
            scanner.return_value.collect=AsyncMock(side_effect=collect)
            github.return_value.publish=AsyncMock(return_value=publication)
            self.bot.start_sync(all_events=True,channel=self.hub)
            await self.bot.scan_task
            github.return_value.publish.assert_awaited_once_with([good])
            self.assertEqual(self.bot.progress.state,'completed with errors')
            before=self.bot.store.question(key=self.bot.store.rows('SELECT key FROM questions')[0]['key'])
            async def retry(*args,**kw):
                self.assertEqual([r['url'] for r in kw['catalog']],[bad.url])
                await kw['on_catalog'](kw['catalog'],True)
                await kw['on_challenge'](bad,None)
                return ScanResult(challenges=[bad])
            scanner.return_value.collect.side_effect=retry
            await self.bot.resume_interaction(self.interaction(),retry=True)
            await self.bot.scan_task
            self.assertEqual(self.bot.store.question(key=before['key'])['thread_id'],before['thread_id'])
            self.assertEqual(len(self.bot.store.rows('SELECT * FROM questions')),2)
            self.assertEqual(self.bot.progress.state,'completed')

    async def test_pause_restart_resume_uses_saved_complete_snapshot(self):
        c=challenge(); other=replace(c,url=c.url[:-24]+'4'*24,title='Second (Easy)')
        captured=asyncio.Event()
        async def collect(*args,**kw):
            await kw['on_catalog']([entry(c),entry(other)],True)
            await kw['on_challenge'](c,None)
            captured.set(); await asyncio.Event().wait()
        with patch('bots.skyline_archive.bot.Scanner') as scanner,patch('bots.skyline_archive.bot.GitHub') as github:
            scanner.return_value.collect=AsyncMock(side_effect=collect)
            github.return_value.publish=AsyncMock(return_value=SimpleNamespace(changed=0,commit_url=None,manifest={}))
            self.bot.start_sync(all_events=True,channel=self.hub)
            await captured.wait(); self.bot.pause_sync()
            await asyncio.gather(self.bot.scan_task,return_exceptions=True)
            self.assertTrue(self.bot.store.get('schedule_hold'))
            self.assertEqual(len(self.bot.jobs.items(1,'collected')),1)
            self.assertEqual(len(self.bot.store.rows('SELECT * FROM posts')),0)
            # Simulate a new SQLite connection after process restart.
            self.bot.store.close(); self.bot.store=Store(self.tmp.name); self.bot.jobs=Jobs(self.bot.store)
            self.bot.preferences.store=self.bot.store; self.bot.attachments.store=self.bot.store
            self.bot.archive.store=self.bot.store
            async def remaining(*args,**kw):
                self.assertEqual([r['url'] for r in kw['catalog']],[other.url])
                await kw['on_catalog'](kw['catalog'],True)
                await kw['on_challenge'](other,None)
                return ScanResult(challenges=[other])
            scanner.return_value.collect.side_effect=remaining
            await self.bot.resume_interaction(self.interaction())
            await self.bot.scan_task
            self.assertFalse(self.bot.store.get('schedule_hold'))
            self.assertEqual(len(self.bot.jobs.items(1,'published')),2)
            self.assertEqual(len(self.bot.store.rows('SELECT * FROM questions')),2)

    async def test_waiting_event_reuses_one_message_and_pings_once_on_open(self):
        self.bot.store.save_settings(dict(enabled=True,frequency=10,notification_channel=self.hub.id))
        url='https://cyberskyline.com/world/'+'1'*24
        with patch('bots.skyline_archive.bot.Scanner') as scanner,patch('bots.skyline_archive.bot.GitHub') as github:
            scanner.return_value.collect=AsyncMock(return_value=ScanResult(waiting_events=[dict(url=url,name='Future event')]))
            for _ in range(2):
                self.bot.start_sync(url,channel=self.hub,scheduled=True); await self.bot.scan_task
            self.assertEqual(len(self.hub.messages),1)
            self.assertEqual(self.bot.progress.state,'waiting for event')
            self.assertIn('Next scheduled check',self.bot.archive_status)
            async def opened(*args,**kw):
                await kw['on_catalog']([entry(challenge())],True)
                await kw['on_challenge'](challenge(),None)
                return ScanResult(challenges=[challenge()])
            scanner.return_value.collect.side_effect=opened
            github.return_value.publish=AsyncMock(return_value=SimpleNamespace(changed=0,commit_url=None,manifest={}))
            for _ in range(2):
                self.bot.start_sync(url,channel=self.hub,scheduled=True); await self.bot.scan_task
            alerts=[m for m in self.hub.messages.values() if 'watched event is open' in m.content]
            self.assertEqual(len(alerts),1)

    async def test_discord_failure_keeps_successful_challenge_and_retry_checkpoint(self):
        a=challenge(); b=replace(a,url=a.url[:-24]+'4'*24)
        async def collect(*args,**kw):
            await kw['on_catalog']([entry(a),entry(b)],True)
            for c in (a,b): await kw['on_challenge'](c,None)
            return ScanResult(challenges=[a,b])
        real=self.bot.archive.publish
        async def publish(items,progress):
            if items[0]==b: raise ArchiveError('Channel is full')
            await real(items,progress)
        with patch('bots.skyline_archive.bot.Scanner') as scanner,patch('bots.skyline_archive.bot.GitHub') as github,patch.object(self.bot.archive,'publish',side_effect=publish):
            scanner.return_value.collect=AsyncMock(side_effect=collect)
            github.return_value.publish=AsyncMock(return_value=SimpleNamespace(changed=0,commit_url=None,manifest={}))
            self.bot.start_sync(all_events=True,channel=self.hub); await self.bot.scan_task
        self.assertEqual(len(self.bot.jobs.items(1,'published')),1)
        self.assertEqual(len(self.bot.jobs.items(1,'failed')),1)

    async def test_failed_file_retries_download_without_losing_question_posts(self):
        c=challenge()
        async def collect(*args,**kw):
            await kw['on_catalog']([entry(c)],True)
            await kw['on_challenge'](c,None)
            self.bot.store.attachment('failed-file',challenge_key=c.key,name='file.bin',source=c.url,status='unavailable',error='HTTP 503')
            return ScanResult(challenges=[c])
        with patch('bots.skyline_archive.bot.Scanner') as scanner,patch('bots.skyline_archive.bot.GitHub') as github:
            scanner.return_value.collect=AsyncMock(side_effect=collect)
            github.return_value.publish=AsyncMock(return_value=SimpleNamespace(changed=0,commit_url=None,manifest={}))
            self.bot.start_sync(all_events=True,channel=self.hub); await self.bot.scan_task
        q=self.bot.store.rows('SELECT * FROM questions')[0]
        self.assertIsNotNone(q['thread_id'])
        self.assertEqual(self.bot.jobs.items(1)[0]['state'],'failed')
        self.bot.jobs.prepare_resume(1)
        self.assertEqual(self.bot.jobs.items(1)[0]['state'],'pending')
        self.assertEqual(self.bot.store.question(key=q['key'])['thread_id'],q['thread_id'])

    async def test_evidence_is_scoped_to_question_and_not_reposted(self):
        c=replace(challenge(),questions=('One?','Two?'),question_ids=('a','b'))
        await self.bot.archive.publish([c])
        qs=[self.bot.store.question(key=r['key']) for r in self.bot.store.rows('SELECT key FROM questions')]
        path=self.bot.attachments.root/'output.txt'; path.write_bytes(b'Synthetic evidence')
        self.bot.store.attachment('extra',challenge_key=c.key,name='output.txt',source='',status='ready',path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        with self.bot.store.db:
            self.bot.store.db.execute("INSERT INTO evidence VALUES('extra',?,456,?,NULL,'fixture')",(qs[0]['key'],qs[0]['thread_id']))
        self.assertEqual(len(self.bot.verifier.payload(qs[0],'')['files']),1)
        self.assertEqual(self.bot.verifier.payload(qs[1],'')['files'],[])
        before=self.guild.counter
        await self.bot.archive.publish([c])
        self.assertEqual(before,self.guild.counter)

    async def test_evidence_rejects_another_users_upload(self):
        q,i=await self.question()
        msg=await i.channel.send('Other person'); msg.author=SimpleNamespace(id=789,bot=False); msg.attachments=[object()]
        with self.assertRaises(ArchiveError): await evidence(self.bot,i,message_id=str(msg.id))
        self.assertEqual(self.bot.store.rows('SELECT * FROM evidence'),[])

    async def test_hint_saves_separate_record_without_verification_status(self):
        q,i=await self.question()
        self.bot.verifier.explain=AsyncMock(return_value=dict(outcome='Inconclusive',method='fixture',evidence='Inspect metadata first.'))
        await assistance(self.bot,i,'hint')
        self.assertIsNone(self.bot.store.latest_verification(q['key']))
        self.assertEqual(len(self.bot.store.rows('SELECT * FROM assistance')),1)
        self.assertIn('Suggestions, not a verified answer',list(i.channel.messages.values())[-1].content)

    async def test_health_ai_test_never_records_a_fake_answer(self):
        self.bot.ai.health=AsyncMock(return_value='Connected')
        with patch('bots.skyline_archive.operations.Scanner') as scanner,patch('bots.skyline_archive.operations.GitHub') as github,patch.object(self.bot,'get_guild',return_value=self.guild):
            scanner.return_value.validate_session=AsyncMock(return_value=True)
            github.return_value.request=AsyncMock(return_value={'permissions':{'push':True}})
            i=self.interaction(); await health(self.bot,i,True)
        self.assertIn('OpenAI: Connected',i.followup.send.call_args.args[0])
        self.assertEqual(self.bot.store.rows('SELECT * FROM verifications'),[])
        self.assertFalse(self.bot.store.get('auth_invalid'))

    async def test_new_commands_are_still_owner_restricted(self):
        commands=SkylineCommands(self.bot)
        for name in ('pause','resume','retry-failed','health','evidence','hint','explain','reorganize'):
            self.assertIsNotNone(commands.get_command(name))
        i=self.interaction(); i.user=Identity(987)
        self.assertFalse(await commands.interaction_check(i))


class SmallUpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_v2_database_migration_keeps_search_answers_and_old_thread_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory); q=store.upsert_challenge(challenge())[0]
            store.link_question(q['key'],10,11,12)
            store.verification(q['key'],' Exact\n',456,dict(outcome='Inconclusive',method='old',evidence='old evidence'))
            store.synced(challenge().key)
            store.db.executescript('DROP TABLE evidence; DROP TABLE assistance; DROP TABLE question_locations; DROP TABLE snapshots; DROP TABLE scan_items; DROP TABLE scan_jobs; PRAGMA user_version=2;')
            store.close(); store=Store(directory)
            self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertTrue((Path(directory)/'archive.before-v3.sqlite3').exists())
            self.assertEqual(store.question(thread_id=12)['key'],q['key'])
            self.assertEqual(store.latest_verification(q['key'])['answer'],' Exact\n')
            self.assertEqual(len(store.search('example',{},[10])),1)
            self.assertEqual(store.snapshot(challenge().key).questions,challenge().questions)
            self.assertIsNotNone(store.one('SELECT synced_fingerprint FROM challenges')['synced_fingerprint'])
            store.close()

    async def test_terminal_elapsed_freezes_and_eta_clears(self):
        p=Progress(state='scanning',started=10,scan_started=10,total=20,processed=10)
        with patch('bots.skyline_archive.progress.time.monotonic',return_value=100): p.update(state='failed')
        with patch('bots.skyline_archive.progress.time.monotonic',return_value=1000): text=p.render()
        self.assertIn('Elapsed:** 90s',text); self.assertIn('Remaining:** not available',text)

    async def test_hint_cannot_request_verification_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            config=SimpleNamespace(openai_api_key='fixture',openai_model='fixture',ai_daily_requests=10)
            request=AsyncMock(return_value=tool_response(operation='verify'))
            ai=OpenAIAssistant(store,config,request)
            tool=AsyncMock()
            payload=dict(question='Synthetic?',instructions='',answer='',mode='hint',files=[dict(name='file',path='unused')])
            result=await ai.assist(payload,dict(evidence=''),tool)
            self.assertEqual(result['outcome'],'Verification error'); tool.assert_not_awaited()
            self.assertNotIn('verify',request.call_args.args[0]['tools'][0]['parameters']['properties']['operation']['enum'])
            store.close()

    async def test_explain_model_opinion_never_becomes_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            ai=OpenAIAssistant(store,SimpleNamespace(openai_api_key='fixture',openai_model='fixture'),AsyncMock(return_value=final_response(assessment='supported',suggested_answer='hidden candidate')))
            result=await ai.assist(dict(question='Synthetic?',instructions='',answer='',mode='explain',files=[]),dict(evidence=''),AsyncMock())
            self.assertEqual(result['outcome'],'Inconclusive'); self.assertNotIn('hidden candidate',result['evidence'])
            store.close()

    async def test_interactive_page_is_diagnosed_without_waiting_or_submitting(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner=Scanner(settings(directory))
            scanner.page=SimpleNamespace(url=challenge().url,goto=AsyncMock(return_value=SimpleNamespace(status=200)),
                evaluate=AsyncMock(return_value={'interactive':True}))
            with self.assertRaisesRegex(ArchiveError,'no replies were submitted'):
                await scanner.visit(challenge().url,'challenge')

    async def test_large_file_bounded_preview_and_explicit_verification_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'large.bin'; p.write_bytes(b'A'*100)
            payload=dict(root=directory,question='What is in this file?',instructions='',answer='candidate',
                files=[dict(name=p.name,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())])
            with patch('bots.skyline_archive.verify_worker.LIMIT',64):
                self.assertEqual(check(payload)['outcome'],'Inconclusive')
                report=inspect_evidence({**payload,'inspect':dict(file_id=0,operation='file_facts')})
                self.assertEqual(report['size'],100)
                self.assertIn('error',inspect_evidence({**payload,'inspect':dict(file_id=0,operation='metadata')}))


class CacheUpgradeTests(fixtures.AttachmentTests):
    async def test_discord_evidence_streams_caches_and_keeps_source_credentials_out(self):
        q=self.store.question(key=self.store.rows('SELECT key FROM questions')[0]['key'])
        upload=SimpleNamespace(id=200,filename='../evidence.txt',url='https://cdn.discordapp.com/attachments/synthetic',size=5)
        session=SimpleNamespace(get=unittest.mock.Mock(return_value=self.response()))
        manager=AsyncMock(); manager.__aenter__.return_value=session
        with patch('aiohttp.ClientSession',return_value=manager) as create,patch('aiohttp.TCPConnector'):
            row=await self.files.evidence(q,upload,456,20)
            repeated=await self.files.evidence(q,upload,456,20)
        self.assertEqual(row['key'],repeated['key']); self.assertEqual(row['name'],'evidence.txt')
        self.assertEqual(Path(row['path']).read_bytes(),b'hello')
        self.assertEqual(create.call_count,1)
        self.assertNotIn('cookie_jar',create.call_args.kwargs)
        self.assertEqual(self.store.one('SELECT * FROM evidence')['question_key'],q['key'])

    async def test_cache_budget_failure_preserves_old_files_and_cleans_part(self):
        original=self.files.root/'original'; original.write_bytes(b'12345')
        with patch.object(self.files,'limits',return_value=(100,8)):
            row,_=await self.fetch_with([self.response(chunks=(b'123456',))])
        self.assertEqual(row['status'],'cache-full')
        self.assertEqual(original.read_bytes(),b'12345'); self.assertEqual(list(self.files.temp.iterdir()),[])

    async def test_discord_evidence_origin_and_size_checks(self):
        q=self.store.question(key=self.store.rows('SELECT key FROM questions')[0]['key'])
        upload=SimpleNamespace(id=100,filename='../file.txt',url='https://example.test/private',size=1)
        row=await self.files.evidence(q,upload,456,20)
        self.assertEqual(row['status'],'failed'); self.assertEqual(row['source'],'')
        upload.url='https://cdn.discordapp.com/attachments/example'; upload.size=100
        row=await self.files.evidence(q,upload,456,20)
        self.assertEqual(row['status'],'failed'); self.assertIn('limit',row['error'])
