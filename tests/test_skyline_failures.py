"""Owner diagnostics use persisted synthetic failures and never contact Discord."""

from dataclasses import replace
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import test_skyline_features as fixtures
if fixtures.discord is None:
    raise unittest.SkipTest('Install optional bot dependencies for failure report tests')
from bots.skyline_archive.bot import SkylineCommands
from bots.skyline_archive.jobs import Jobs
from bots.skyline_archive.storage import Store
from bots.skyline_archive.ui import FailuresView, diagnostic_text, failure_help


class FailureReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name)
        self.client=SimpleNamespace(store=self.store,jobs=Jobs(self.store),settings=fixtures.settings(self.tmp.name))

    async def asyncTearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def scan(self,count=2):
        ident=self.client.jobs.create({},False)
        entries=[]
        for n in range(count):
            c=replace(fixtures.challenge(),url=fixtures.challenge().url[:-24]+f'{n+3:024x}',title=f'Challenge {n+1}')
            entries.append(dict(url=c.url,title=c.title,category=c.category,event=c.event))
        self.client.jobs.catalog(ident,entries)
        for e in entries:
            self.client.jobs.state(ident,e['url'],'failed','Cyber Skyline timed out; check the connection and retry.')
        return ident,entries

    def interaction(self,owner=456,guild=123):
        return SimpleNamespace(user=SimpleNamespace(id=owner),guild_id=guild,
            response=SimpleNamespace(send_message=AsyncMock(),edit_message=AsyncMock()))

    async def test_active_scan_report_reads_reasons_without_mutating_or_loading_payload(self):
        ident,entries=self.scan()
        before=self.store.db.total_changes
        view=FailuresView(self.client,456)
        text=view.render()
        self.assertIn('Failed challenges:** 2',text)
        self.assertIn('Page/network error: 2',text)
        self.assertIn(entries[0]['url'],text)
        self.assertIn('Scan started:',text)
        self.assertIn('timed out',text)
        self.assertEqual(self.store.db.total_changes,before)
        self.assertNotIn('payload',self.client.jobs.failures(ident)[1][0])
        self.assertTrue(view.children[0].disabled)
        self.assertFalse(view.children[1].disabled)

    async def test_report_survives_restart_and_pins_scan_while_newer_run_exists(self):
        ident,entries=self.scan()
        self.store.close()
        self.store=Store(self.tmp.name)
        self.client.store=self.store
        self.client.jobs=Jobs(self.store)
        view=FailuresView(self.client,456)
        view.render()
        newer,_=self.scan(1)
        await view.children[1].callback(self.interaction())
        text=view.render()
        self.assertIn(f'scan {ident}',text)
        self.assertIn('Item 2/2',text)
        self.assertEqual(FailuresView(self.client,456).render().splitlines()[0],f'**WS failures — scan {newer}**')

    async def test_refresh_after_retry_clamps_page_and_does_not_claim_success(self):
        ident,entries=self.scan(3)
        view=FailuresView(self.client,456,ident)
        view.page=2
        view.render()
        for e in entries[1:]:
            self.client.jobs.state(ident,e['url'],'published')
        self.assertIn('Item 1/1',view.render())
        self.assertTrue(view.children[1].disabled)
        self.client.jobs.state(ident,entries[0]['url'],'pending')
        self.assertIn('No failed challenge records remain',view.render())
        self.assertEqual(self.client.jobs.items(ident)[0]['state'],'pending')

    async def test_command_and_buttons_reject_nonowners_and_other_servers(self):
        self.scan()
        commands=SkylineCommands(self.client)
        command=commands.get_command('failures')
        self.assertIsNotNone(command)
        view=FailuresView(self.client,456)
        for i in (self.interaction(owner=789),self.interaction(guild=999)):
            self.assertFalse(await commands.interaction_check(i))
            self.assertFalse(await view.interaction_check(i))
        owner=self.interaction()
        await command.callback(commands,owner)
        self.assertTrue(owner.response.send_message.call_args.kwargs['ephemeral'])

    async def test_interactive_error_explains_retry_limitation(self):
        ident,entries=self.scan(1)
        self.client.jobs.state(ident,entries[0]['url'],'failed','Interactive conversation: later questions require submitted answers.')
        text=FailuresView(self.client,456).render()
        self.assertIn('Interactive challenge: 1',text)
        self.assertIn('Automatic retries cannot reveal them',text)
        self.assertIn('no answers were submitted',text)

    async def test_attachment_details_exclude_private_evidence_and_secrets(self):
        ident,entries=self.scan(1)
        c=replace(fixtures.challenge(),url=entries[0]['url'])
        q=self.store.upsert_challenge(c)[0]
        self.store.attachment('source',challenge_key=c.key,name='sample.bin',source='',status='cache-full',error='Private cache budget reached.')
        self.store.attachment('private',challenge_key=c.key,name='private-evidence.bin',source='',status='failed',error='Secret evidence')
        with self.store.db:
            self.store.db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?)',('private',q['key'],456,100,101,'2026-01-01'))
        text=FailuresView(self.client,456,ident).render()
        self.assertIn('sample.bin',text)
        self.assertIn('cache-full',text)
        self.assertNotIn('private-evidence',text)
        self.assertNotIn('Secret evidence',text)

    async def test_sanitization_and_invalid_source_link(self):
        ident,entries=self.scan(1)
        self.client.settings.github_token='synthetic-secret-value'
        error='synthetic-secret-value\nAuthorization: Bearer bad-header\nCookie: login=private-cookie\nhttps://example.test/file?signature=private-query\npassword=private-password @everyone'
        self.client.jobs.state(ident,entries[0]['url'],'failed',error)
        with self.store.db:
            self.store.db.execute('UPDATE scan_items SET url=?,entry=? WHERE scan_id=?',
                ('https://example.test/?private-query',json.dumps(dict(title=error)),ident))
        text=FailuresView(self.client,456).render()
        for secret in ('synthetic-secret-value','bad-header','private-cookie','private-query','private-password','@everyone'):
            self.assertNotIn(secret,text)
        self.assertNotIn('[Open challenge]',text)
        self.assertLessEqual(len(text),1950)

    async def test_no_failures_unknown_scan_and_run_level_error_are_honest(self):
        self.assertEqual(FailuresView(self.client,456).render(),'No saved failed scan was found.')
        ident=self.client.jobs.create({},True)
        with self.store.db:
            self.store.db.execute("UPDATE scans SET state='failed',channel_id=10,message_id=20 WHERE id=?",(ident,))
        text=FailuresView(self.client,456).render()
        self.assertIn('run-level/discovery error',text)
        self.assertIn('https://discord.com/channels/123/10/20',text)
        self.assertEqual(FailuresView(self.client,456,99999).render(),'No saved failed scan was found.')

    def test_repair_hints_do_not_treat_tool_failure_as_incorrect_answer(self):
        for error,label in [('Forbidden','Discord destination'),('Private cache full','File/cache limit'),
                            ('Files need retry','Attachment problem'),('Expected content missing','Unsupported or incomplete page')]:
            self.assertEqual(failure_help(error)[0],label)
        self.assertNotIn('incorrect',failure_help('Unknown error')[1])
