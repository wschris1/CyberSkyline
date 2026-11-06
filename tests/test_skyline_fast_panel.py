"""Synthetic fast-mode and private control-panel tests; never contact live services."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import AsyncMock, patch

import test_skyline_features as fixtures
if fixtures.discord is None:
    raise unittest.SkipTest('Install the optional bot requirements')
from test_skyline_features import challenge
import test_skyline_workflows as workflow_fixtures
from bots.skyline_archive.core import ArchiveError, AttachmentRef, SessionExpired
from bots.skyline_archive.panel import PanelBridge, configuration
from bots.skyline_archive.scanner import ScanResult
from bots.skyline_archive.storage import Store, digest
from bots.skyline_archive.workflows import catalog_entry


class FastTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=workflow_fixtures.WorkflowTests.asyncSetUp
    asyncTearDown=workflow_fixtures.WorkflowTests.asyncTearDown
    collect=workflow_fixtures.WorkflowTests.collect
    run_job=workflow_fixtures.WorkflowTests.run_job
    interaction=workflow_fixtures.WorkflowTests.interaction

    async def asyncSetUp(self):
        await workflow_fixtures.WorkflowTests.asyncSetUp(self)
        @asynccontextmanager
        async def opened():
            yield object()
        self.source.return_value.opened=opened
        self.c=replace(challenge(),attachment_refs=(AttachmentRef('evidence.txt','https://cyberskyline.com/artifact/sample'),))

    async def ready(self,c,ref,context):
        row=self.bot.attachments.defer(c,ref)
        path=self.bot.attachments.root/(row['key']+'.txt')
        path.write_text('synthetic evidence')
        return self.bot.store.attachment(row['key'],status='ready',path=str(path),size=18,sha256='synthetic-hash',error=None)

    async def test_all_questions_exist_before_download_and_file_links_replace_pending(self):
        second=replace(self.c,url=self.c.url[:-24]+'4'*24,title='Second (Easy)')
        self.collect(self.c,second)
        async def fetch(c,ref,context):
            questions=self.bot.store.rows('SELECT * FROM questions')
            self.assertEqual(len(questions),2)
            self.assertTrue(all(q['thread_id'] for q in questions))
            return await self.ready(c,ref,context)
        with patch.object(self.bot.attachments,'fetch',side_effect=fetch):
            await self.run_job('discord',fast_comp=True)
        self.assertEqual(self.bot.progress.state,'completed')
        self.assertEqual(self.bot.progress.files_deferred,0)
        self.assertEqual(self.bot.progress.discord_completed,2)
        self.assertTrue(all(r['state']=='published' for r in self.bot.jobs.items(1)))
        for q in self.bot.store.rows('SELECT * FROM questions'):
            parent=self.guild.channels[q['channel_id']].messages[q['message_id']]
            self.assertNotIn('queued for the file phase',parent.embeds[0].description)
            self.assertIn('evidence.txt',parent.embeds[0].description)
        self.remote.assert_not_called()

    async def test_fast_preview_never_creates_files_posts_or_delivery_markers(self):
        self.collect(self.c)
        with patch.object(self.bot.attachments,'fetch',new=AsyncMock()) as fetch:
            await self.run_job('discord',fast_comp=True,preview=True)
        fetch.assert_not_called()
        for table in ('challenges','questions','attachments','deliveries','posts'):
            self.assertEqual(self.bot.store.rows('SELECT * FROM '+table),[])

    async def test_download_failure_retry_preserves_threads_and_does_not_reread_questions(self):
        self.collect(self.c)
        async def failed(c,ref,context):
            row=self.bot.attachments.defer(c,ref)
            return self.bot.store.attachment(row['key'],status='failed',error='Synthetic unavailable file')
        with patch.object(self.bot.attachments,'fetch',side_effect=failed):
            await self.run_job('discord',fast_comp=True)
        self.assertEqual(self.bot.progress.state,'completed with errors')
        before=self.bot.store.rows('SELECT key,message_id,thread_id FROM questions')
        self.assertTrue(self.bot.jobs.items(1)[0]['payload'])
        self.collect()
        with patch.object(self.bot.attachments,'fetch',side_effect=self.ready):
            await self.bot.resume_interaction(self.interaction(),retry=True)
            await self.bot.scan_task
        self.assertEqual(self.bot.progress.state,'completed')
        self.assertEqual(before,self.bot.store.rows('SELECT key,message_id,thread_id FROM questions'))
        self.assertTrue(self.bot.scan_options['fast_comp'])

    async def test_stop_during_files_keeps_text_ready_checkpoint_and_resumes(self):
        entered=asyncio.Event()
        async def waiting(*args):
            entered.set()
            await asyncio.Event().wait()
        self.collect(self.c)
        with patch.object(self.bot.attachments,'fetch',side_effect=waiting):
            self.bot.start_sync(all_events=True,workflow='discord',channel=self.hub,fast_comp=True)
            await asyncio.wait_for(entered.wait(),2)
            old=self.bot.store.rows('SELECT * FROM questions')
            self.bot.stop_sync()
            with self.assertRaises(asyncio.CancelledError):
                await self.bot.scan_task
        self.assertEqual(self.bot.jobs.items(1)[0]['state'],'text-ready')
        self.collect()
        with patch.object(self.bot.attachments,'fetch',side_effect=self.ready):
            await self.bot.resume_interaction(self.interaction())
            await self.bot.scan_task
        self.assertEqual(old,self.bot.store.rows('SELECT * FROM questions'))
        self.assertEqual(self.bot.progress.state,'completed')

    async def test_auth_expiry_during_deferred_files_preserves_questions_and_latches(self):
        self.collect(self.c)
        with patch.object(self.bot.attachments,'fetch',side_effect=SessionExpired('Refresh login')):
            await self.run_job('discord',fast_comp=True)
        self.assertTrue(self.bot.store.get('auth_invalid'))
        self.assertTrue(self.bot.store.rows('SELECT thread_id FROM questions')[0]['thread_id'])
        self.assertEqual(self.bot.jobs.items(1)[0]['state'],'text-ready')
        self.assertEqual(self.bot.progress.state,'waiting for login')

    async def test_fast_comp_setting_persists_restart_without_schema_or_data_loss(self):
        self.bot.store.save_settings({'fast_comp':True})
        copy=Store(self.bot.settings.state_dir)
        self.assertTrue(copy.get('fast_comp',False,'settings'))
        copy.close()
        self.collect(challenge())
        await self.run_job('discord')
        self.assertTrue(self.bot.progress.fast_comp)

    async def test_fast_combined_publishes_github_after_files(self):
        self.collect(self.c)
        async def publish(items):
            self.assertEqual(self.bot.jobs.items(1)[0]['state'],'published')
            from types import SimpleNamespace
            return SimpleNamespace(changed=0,commit_url=None,manifest={})
        self.remote.return_value.publish.side_effect=publish
        with patch.object(self.bot.attachments,'fetch',side_effect=self.ready):
            await self.run_job('both',fast_comp=True)
        self.assertEqual(self.bot.progress.state,'completed')
        self.remote.return_value.publish.assert_awaited_once()


class PanelTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=workflow_fixtures.WorkflowTests.asyncSetUp
    asyncTearDown=workflow_fixtures.WorkflowTests.asyncTearDown
    collect=workflow_fixtures.WorkflowTests.collect

    def setup_panel(self):
        p=self.bot.settings.state_dir/'panel.json'
        config=dict(url='https://test.chatgpt.site',owner_id=456,service_token='test-service-token-'*4,agent_token='test-agent-token-'*4)
        p.write_text(json.dumps(config))
        self.bot.panel=PanelBridge(self.bot)
        return p

    def command(self,action,**payload):
        return dict(id=str(uuid.uuid4()),owner_id='456',expires=time.time()+120,action=action,payload=payload)

    async def test_configuration_fails_closed_for_wrong_origin_and_owner(self):
        p=self.setup_panel()
        data=json.loads(p.read_text())
        for url in ('http://test.chatgpt.site','https://evil.example','https://test.chatgpt.site@evil.example','https://test.chatgpt.site/path','https://test.chatgpt.site?token=hidden'):
            p.write_text(json.dumps({**data,'url':url}))
            with self.assertRaises(ArchiveError):configuration(p,{456})
        p.write_text(json.dumps({**data,'owner_id':999}))
        with self.assertRaises(ArchiveError):configuration(p,{456})

    async def test_duplicate_delivery_never_starts_twice_across_new_bridge(self):
        self.setup_panel();self.collect(challenge())
        cmd=self.command('scan-discord',all_events=True,fast_comp=True)
        first=await self.bot.panel.execute(cmd)
        self.assertTrue(first['ok'])
        await self.bot.scan_task
        second=await PanelBridge(self.bot).execute(cmd)
        self.assertEqual(first,second)
        self.assertEqual(len(self.bot.store.rows('SELECT * FROM scans')),1)

    async def test_expired_wrong_owner_and_unknown_action_are_rejected(self):
        self.setup_panel()
        commands=[{**self.command('stop'),'expires':time.time()-1},
                  {**self.command('stop'),'owner_id':'999'},self.command('delete-everything')]
        for cmd in commands:self.assertFalse((await self.bot.panel.execute(cmd))['ok'])
        self.assertFalse(self.bot.busy())

    async def test_settings_use_validation_and_persist(self):
        self.setup_panel()
        with patch.object(self.bot,'get_guild',return_value=self.guild):
            bad=await self.bot.panel.execute(self.command('settings',frequency=1))
            good=await self.bot.panel.execute(self.command('settings',frequency=10,fast_comp=True))
        self.assertFalse(bad['ok']);self.assertTrue(good['ok'])
        self.assertTrue(self.bot.preferences.effective()['fast_comp'])
        self.assertEqual(self.bot.preferences.effective()['frequency'],10)

    async def test_snapshot_omits_credentials_answers_and_source_text(self):
        self.setup_panel()
        c=replace(challenge(),prompt='PRIVATE SOURCE CONTENT')
        q=self.bot.store.upsert_challenge(c)[0]
        self.bot.store.verification(q['key'],'SECRET ANSWER',456,dict(method='fixture',outcome='Inconclusive',evidence='PRIVATE EVIDENCE'))
        text=json.dumps(self.bot.panel.snapshot())
        for value in ('SECRET ANSWER','PRIVATE SOURCE CONTENT','PRIVATE EVIDENCE','test-agent-token-','test-service-token-'):
            self.assertNotIn(value,text)

    async def test_panel_and_discord_share_same_scan_lock(self):
        self.setup_panel()
        self.source.return_value.collect=AsyncMock(side_effect=lambda *a,**k: asyncio.sleep(20))
        # A real pending task occupies the same shared lock checked by panel actions.
        self.bot.scan_task=asyncio.create_task(asyncio.sleep(20))
        result=await self.bot.panel.execute(self.command('scan-discord',all_events=True))
        self.assertFalse(result['ok']);self.assertIn('already running',result['message'])
        self.bot.scan_task.cancel()
        await asyncio.gather(self.bot.scan_task,return_exceptions=True)

    async def test_interrupted_receipt_is_not_executed_again(self):
        self.setup_panel();cmd=self.command('stop')
        saved=dict(id=cmd['id'],ok=False,message='Interrupted before confirmation')
        self.bot.store.put('panel-receipts',{cmd['id']:saved})
        with patch.object(self.bot,'stop_sync') as stop:
            self.assertEqual(await self.bot.panel.execute(cmd),saved)
        stop.assert_not_called()
