"""Synthetic regression tests. Nothing in this suite posts to a live service."""

import asyncio
import base64
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bots.skyline_archive.core import ArchiveError, AttachmentRef, Challenge, SessionExpired, archive_files, MANIFEST
from bots.skyline_archive.storage import Store, fingerprint, now
from bots.skyline_archive.attachments import Attachments, filename, public_url, PublicResolver
from bots.skyline_archive.preferences import Preferences
from bots.skyline_archive.progress import Progress, ProgressMessage
from bots.skyline_archive.scanner import Scanner, ScanResult, matches
from bots.skyline_archive.verification import Verifier, select_answer
from bots.skyline_archive.verify_worker import check

try:
    import discord
    from bots.skyline_archive.bot import SkylineBot, SkylineCommands, SessionCommands
    from bots.skyline_archive.discord_archive import DiscordArchive
    from bots.skyline_archive.ui import Picker, SearchView
except ModuleNotFoundError as exc:
    if exc.name not in ('discord','aiohttp'):
        raise
    discord=None


def challenge(**values):
    base=dict(url='https://cyberskyline.com/module/'+'1'*24+'/'+'2'*24+'/'+'3'*24,
        event='NCL Spring 2026 Practice Game',category='Password Cracking',title='Synthetic example (Easy)',
        prompt='Use the supplied evidence.',questions=('Q1 - 10 points\nWhat is the example value?',),question_ids=('abc',))
    return Challenge(**{**base,**values})


def settings(directory):
    return SimpleNamespace(guild_id=123,owners={456},repository='example/archive',branch='main',interval=0,
        event_url='',delay=1,max_challenges=2000,state_dir=Path(directory),auth_file=Path(directory)/'auth.json',headless=True,
        default_preview=False,message_content=False)


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name)

    async def asyncTearDown(self):
        self.store.close(); self.tmp.cleanup()

    async def test_restart_retains_all_relationships_and_answers(self):
        q=self.store.upsert_challenge(challenge())[0]
        self.store.link_question(q['key'],100,101,102)
        self.store.map('category','password cracking',99)
        self.store.verification(q['key'],' space\nCase! ',456,dict(method='fixture',outcome='Inconclusive',evidence='No proof.'))
        self.store.synced(challenge().key)
        self.store.close(); self.store=Store(self.tmp.name)
        self.assertEqual(self.store.question(thread_id=102)['message_id'],101)
        self.assertEqual(self.store.mapping('category','password cracking'),99)
        self.assertEqual(self.store.latest_verification(q['key'])['answer'],' space\nCase! ')

    async def test_legacy_import_indexes_without_sync_markers_or_posts(self):
        c=replace(challenge(),question_ids=())
        files=archive_files([c])
        count=await self.store.import_manifest(files[MANIFEST],AsyncMock(side_effect=lambda p:files[p]))
        self.assertEqual(count,1)
        self.assertEqual(self.store.rows('SELECT * FROM posts'),[])
        self.assertIsNone(self.store.one('SELECT synced_fingerprint FROM challenges')['synced_fingerprint'])
        rows=self.store.search('example',{},[],include_legacy=True)
        self.assertEqual(len(rows),1)
        old_key=rows[0]['key']
        self.store.upsert_challenge(challenge())
        self.assertEqual(self.store.rows('SELECT * FROM questions')[0]['key'],old_key)
        self.assertEqual(len(self.store.rows('SELECT * FROM questions')),1)

    async def test_search_filters_visibility_and_literal_query(self):
        first=self.store.upsert_challenge(challenge())[0]
        other=challenge(url='https://cyberskyline.com/module/'+'1'*24+'/'+'2'*24+'/'+'4'*24,event='NCL Fall 2026 Team Game')
        second=self.store.upsert_challenge(other)[0]
        self.store.link_question(first['key'],10,11,12)
        self.store.link_question(second['key'],20,21,22)
        self.assertEqual(len(self.store.search('example',{},[10])),1)
        self.assertEqual(self.store.search('example',{'season':'fall-2026'},[10]),[])
        self.assertEqual(len(self.store.search('example',{'competition':'team-game'},[20])),1)
        self.assertEqual(self.store.search('" OR unknown*',{},[10]),[])
        self.assertEqual(self.store.search('example',{},[]),[])

    async def test_duplicate_source_does_not_duplicate_index_or_question(self):
        for _ in range(3): self.store.upsert_challenge(challenge())
        self.assertEqual(len(self.store.rows('SELECT * FROM questions')),1)
        self.assertEqual(len(self.store.rows('SELECT * FROM question_search')),1)
        changed=replace(challenge(),questions=('A revised phrase?',))
        self.store.upsert_challenge(changed)
        self.assertEqual(len(self.store.search('revised',{},[],include_legacy=True)),0)
        self.assertEqual(self.store.rows('SELECT text FROM question_search')[0]['text'],'A revised phrase?')

    async def test_migration_from_v1_keeps_existing_data(self):
        self.store.upsert_challenge(challenge())
        self.store.db.executescript('DROP TRIGGER question_search_insert; DROP TRIGGER question_search_update; DROP TRIGGER challenge_search_title; DROP TABLE question_search; PRAGMA user_version=1;')
        self.store.close(); self.store=Store(self.tmp.name)
        self.assertEqual(len(self.store.rows('SELECT * FROM question_search')),1)
        self.assertTrue((Path(self.tmp.name)/'archive.before-v2.sqlite3').is_file())

    async def test_interrupted_scan_is_recovered_only_once(self):
        with self.store.db:
            self.store.db.execute("INSERT INTO scans(state,preview,scope,progress,started) VALUES('scanning',0,'{}','{}',?)",(now(),))
        self.assertEqual(len(self.store.interrupted_scans()),1)
        self.assertEqual(self.store.interrupted_scans(),[])

    async def test_question_reduction_preserves_discussion(self):
        c=replace(challenge(),questions=('First?','Second?'),question_ids=('a','b'))
        self.store.upsert_challenge(c)
        with self.assertRaises(ArchiveError): self.store.upsert_challenge(challenge())
        self.assertEqual(len(self.store.rows('SELECT * FROM questions')),2)

    async def test_changed_source_identity_stops_instead_of_reassigning_discussion(self):
        q=self.store.upsert_challenge(challenge())[0]
        self.store.link_question(q['key'],1,2,3)
        with self.assertRaises(ArchiveError):
            self.store.upsert_challenge(replace(challenge(),question_ids=('replacement',)))
        self.assertEqual(self.store.question(thread_id=3)['source_id'],'abc')


class ProgressTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_total_never_fabricates_percent_or_eta(self):
        p=Progress(processed=10)
        self.assertIn('unknown (discovering)',p.render())
        self.assertIn('Remaining:** not available',p.render())
        self.assertNotIn('%',p.render())

    async def test_edits_are_throttled_and_same_message_finishes(self):
        p=Progress()
        message=SimpleNamespace(edit=AsyncMock())
        live=ProgressMessage(message,p,True,interval=0.001)
        self.assertEqual(live.interval,5)
        live.start()
        for i in range(100): p.update(processed=i)
        await asyncio.sleep(0)
        message.edit.assert_not_awaited()
        p.update(state='completed')
        await live.finish()
        message.edit.assert_awaited_once()
        self.assertIn('completed',message.edit.call_args.kwargs['content'])

    async def test_eta_only_after_known_total_and_enough_samples(self):
        with patch('bots.skyline_archive.progress.time.monotonic',return_value=100):
            p=Progress(total=10,processed=3,started=70,scan_started=80)
            self.assertIn('about 47s (scan phase only)',p.render())
            p.total=None
            self.assertIn('Remaining:** not available',p.render())


@unittest.skipIf(discord is None,'Install bot requirements for HTTP session fixtures')
class AttachmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name)
        self.files=Attachments(self.store,max_bytes=10)
        self.c=challenge(); self.store.upsert_challenge(self.c)
        self.ref=AttachmentRef('../proof.txt','https://cyberskyline.com/artifact/example')
        self.context=SimpleNamespace(cookies=AsyncMock(return_value=[]))

    async def asyncTearDown(self):
        self.store.close(); self.tmp.cleanup()

    def response(self,status=200,chunks=(b'hello',),headers=None):
        async def stream(n):
            for chunk in chunks: yield chunk
        response=SimpleNamespace(status=status,content_length=None,headers=headers or {},content=SimpleNamespace(iter_chunked=stream))
        manager=AsyncMock(); manager.__aenter__.return_value=response
        return manager

    async def fetch_with(self,responses):
        session=SimpleNamespace(get=unittest.mock.Mock(side_effect=responses))
        manager=AsyncMock(); manager.__aenter__.return_value=session
        with patch('aiohttp.ClientSession',return_value=manager),patch('aiohttp.TCPConnector'):
            result=await self.files.fetch(self.c,self.ref,self.context)
        return result,session

    async def test_streaming_download_cache_and_conditional_revalidation(self):
        row,_=await self.fetch_with([self.response(headers={'ETag':'revision1'})])
        self.assertEqual(row['status'],'ready')
        self.assertEqual(Path(row['path']).read_bytes(),b'hello')
        row,session=await self.fetch_with([self.response(status=304)])
        self.assertEqual(session.get.call_args.kwargs['headers']['If-None-Match'],'revision1')
        self.assertEqual(row['sha256'],hashlib.sha256(b'hello').hexdigest())

    async def test_oversized_stream_cleans_temporary_files(self):
        row,_=await self.fetch_with([self.response(chunks=(b'123456',b'789012'))])
        self.assertEqual(row['status'],'oversized')
        self.assertEqual(list(self.files.temp.iterdir()),[])

    async def test_failure_and_authentication_are_separate(self):
        row,_=await self.fetch_with([self.response(status=503)])
        self.assertEqual(row['status'],'unavailable')
        with self.assertRaises(SessionExpired): await self.fetch_with([self.response(status=401)])
        self.assertEqual(list(self.files.temp.iterdir()),[])

    async def test_redirects_and_safe_names(self):
        self.assertEqual(filename('../../something.txt'),'something.txt')
        self.assertEqual(filename('C:\\private\\CON.txt'),'_CON.txt')
        with self.assertRaises(ArchiveError): public_url('http://localhost/data')
        row,_=await self.fetch_with([self.response(status=302,headers={'Location':'https://127.0.0.1/private'}),self.response()])
        # Resolver is independently tested below; a literal private host must be rejected before a request.
        self.assertNotEqual(row['status'],'ready')

    async def test_private_dns_is_rejected(self):
        with patch.object(asyncio.get_running_loop(),'getaddrinfo',new=AsyncMock(return_value=[(2,1,6,'',('127.0.0.1',443))])):
            with self.assertRaises(ArchiveError): await PublicResolver().resolve('example.test',443)

    async def test_upload_status_does_not_postpone_cache_revalidation(self):
        row,_=await self.fetch_with([self.response()])
        self.store.put('attachment-checked/'+row['key'],(datetime.now(timezone.utc)-timedelta(days=2)).isoformat())
        self.store.attachment(row['key'],status='uploaded')
        updated,session=await self.fetch_with([self.response(chunks=(b'changed',))])
        session.get.assert_called_once()
        self.assertNotEqual(updated['sha256'],row['sha256'])


class VerificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name); self.files=Attachments(self.store)
        self.verifier=Verifier(self.store,self.files)

    async def asyncTearDown(self):
        self.store.close(); self.tmp.cleanup()

    def payload(self,question,answer,instructions='',data=None,name='input.txt'):
        files=[]
        if data is not None:
            path=self.files.root/name; path.write_bytes(data)
            files=[dict(name=name,path=str(path),sha256=hashlib.sha256(data).hexdigest())]
        return dict(question=question,instructions=instructions,answer=answer,files=files,root=str(self.files.root))

    async def test_decode_preserves_case_space_and_special_characters(self):
        data=b'SGkgIQo='
        good=self.payload('What is the decoded base64 value?','Hi !\n',data=data)
        self.assertEqual(check(good)['outcome'],'Verified correct')
        self.assertEqual(check({**good,'answer':'hi !'})['outcome'],'Verified incorrect')

    async def test_unsalted_hash_checks_candidate_without_bruteforce(self):
        digest=hashlib.sha256(b'Case sensitive!').hexdigest()
        payload=self.payload('What is the password?','Case sensitive!',f'The unsalted SHA-256 digest is {digest}')
        self.assertEqual(check(payload)['outcome'],'Verified correct')
        self.assertEqual(check({**payload,'answer':'wrong'})['outcome'],'Verified incorrect')
        self.assertEqual(check({**payload,'question':'What is the length of the password?','answer':'15'})['outcome'],'Inconclusive')

    async def test_timestamp_conversion_requires_a_direct_question(self):
        data=self.payload('Convert timestamp to ISO UTC','1970-01-01T00:00:00.000000Z','Input `0` uses unix-s.')
        self.assertEqual(check(data)['outcome'],'Verified correct')
        data['question']='What is the ISO UTC date one day after the timestamp?'
        self.assertEqual(check(data)['outcome'],'Inconclusive')

    async def test_unsupported_and_invalid_evidence_are_not_wrong_answers(self):
        self.assertEqual(check(self.payload('What is the flag?','ABC'))['outcome'],'Inconclusive')
        payload=self.payload('What is the decoded base64 value?','value',data=b'%%%')
        q=self.store.upsert_challenge(challenge(questions=(payload['question'],),prompt=''))[0]
        f=payload['files'][0]
        self.store.attachment('a',challenge_key=challenge().key,name='input.txt',source='https://cyberskyline.com/artifact/a',
                              status='ready',path=f['path'],sha256=f['sha256'],size=3)
        result=await self.verifier.check(self.store.question(key=q['key']),'value')
        self.assertEqual(result['outcome'],'Verification error')

    async def test_packet_count_is_complete_and_unfiltered(self):
        header=b'\xd4\xc3\xb2\xa1'+struct.pack('<HHIIII',2,4,0,0,65535,1)
        payload=self.payload('How many packets are in the capture?','1',data=header+struct.pack('<IIII',0,0,3,3)+b'abc',name='capture.pcap')
        self.assertEqual(check(payload)['outcome'],'Verified correct')
        self.assertEqual(check({**payload,'question':'How many TCP packets are in the capture?'})['outcome'],'Inconclusive')

    async def test_http_status_adapter(self):
        payload=self.payload('What HTTP status code is shown?','200',data=b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n')
        self.assertEqual(check(payload)['outcome'],'Verified correct')

    async def test_subprocess_uses_repository_adapter(self):
        c=challenge(questions=('What is the decoded hex value?',),prompt='Encoded value: `41202042`')
        q=self.store.upsert_challenge(c)[0]
        value=await self.verifier.check(self.store.question(key=q['key']),'A  B')
        self.assertEqual(value['outcome'],'Verified correct')
        self.assertEqual(value['method'],'tools/decode_value.py')

    async def test_answer_selection_is_not_guessed(self):
        def message(text,ident=456):
            return SimpleNamespace(author=SimpleNamespace(id=ident,bot=False),content=text,created_at=datetime.now(timezone.utc))
        text=' Leading\nSpace! '
        self.assertEqual(select_answer([message(text)],456)[0],text)
        self.assertIsNone(select_answer([message(text),message('discussion')],456)[0])
        self.assertIsNone(select_answer([message(text,789)],456)[0])

    async def test_changed_cached_file_cannot_verify(self):
        payload=self.payload('What is the file size in bytes?','3',data=b'abc')
        Path(payload['files'][0]['path']).write_bytes(b'wrong')
        self.assertEqual(check(payload)['outcome'],'Verification error')

    async def test_derived_questions_do_not_receive_whole_file_verdicts(self):
        cases=[('How many bytes are in the file header?','3'),
               ('What is the decoded base64 value, reversed?','x'),
               ('How many fragmented packets are in the capture?','1'),
               ('What is the initial HTTP status code?','200')]
        for question,answer in cases:
            with self.subTest(question=question):
                self.assertEqual(check(self.payload(question,answer,data=b'abc'))['outcome'],'Inconclusive')

    async def test_encrypted_zip_checks_password_without_extracting(self):
        # Synthetic ZipCrypto fixture; password and content are not competition data.
        raw=base64.b64decode('UEsDBAoACQAAADeKZF1w0t3hLAAAACAAAAAIABwAZGF0YS50eHRVVAkAAynq6mop6upqdXgLAAEEAAAAAAQAAAAAOEoWx+X7D0A0bCrjvvrUt5MAnL9SLq4Q4azJLLb7BUVu5DKg4OJ1bjW3WiBQSwcIcNLd4SwAAAAgAAAAUEsBAh4DCgAJAAAAN4pkXXDS3eEsAAAAIAAAAAgAGAAAAAAAAQAAAKSBAAAAAGRhdGEudHh0VVQFAAMp6upqdXgLAAEEAAAAAAQAAAAAUEsFBgAAAAABAAEATgAAAH4AAAAAAA==')
        data=self.payload('What is the ZIP password?','fixture-only',data=raw,name='encrypted.zip')
        self.assertEqual(check(data)['outcome'],'Verified correct')
        self.assertEqual(check({**data,'answer':'not-the-password'})['outcome'],'Verified incorrect')
        self.assertFalse((self.files.root/'data.txt').exists())

    async def test_timeout_kills_worker_and_returns_error_not_incorrect(self):
        q=self.store.upsert_challenge(challenge())[0]
        process=SimpleNamespace(returncode=None,kill=unittest.mock.Mock(),wait=AsyncMock(),communicate=AsyncMock(side_effect=asyncio.TimeoutError))
        with patch('bots.skyline_archive.verification.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)) as launch:
            value=await self.verifier.check(self.store.question(key=q['key']),'$(untrusted)\nCase')
        self.assertEqual(value['outcome'],'Verification error')
        process.kill.assert_called_once()
        self.assertNotIn('GITHUB_TOKEN',launch.call_args.kwargs['env'])
        self.assertNotIn('$(untrusted)',launch.call_args.args)

    async def test_missing_worker_and_broken_output_are_errors(self):
        q=self.store.upsert_challenge(challenge())[0]
        with patch('bots.skyline_archive.verification.asyncio.create_subprocess_exec',new=AsyncMock(side_effect=FileNotFoundError)):
            value=await self.verifier.check(self.store.question(key=q['key']),'candidate')
        self.assertEqual(value['outcome'],'Verification error')
        process=SimpleNamespace(returncode=1,wait=AsyncMock(),communicate=AsyncMock(return_value=(b'',b'private failure details')))
        with patch('bots.skyline_archive.verification.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)):
            value=await self.verifier.check(self.store.question(key=q['key']),'candidate')
        self.assertEqual(value['outcome'],'Verification error')
        self.assertNotIn('private failure',value['evidence'])


@unittest.skipIf(discord is None,'Install bot requirements for browser boundary fixtures')
class ScannerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_module_waits_for_labels_before_difficulty_filtering(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner=Scanner(settings(directory))
            url=challenge().url
            href=url.removeprefix('https://cyberskyline.com')
            early=dict(category='Password Cracking',links=[dict(href=href,title='')])
            ready=dict(category='Password Cracking',links=[dict(href=href,title='Synthetic example (Hard)')])
            scanner.page=SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=200)),
                url=url,evaluate=AsyncMock(side_effect=[early,ready]),
                locator=lambda _:SimpleNamespace(count=AsyncMock(return_value=1)))
            with patch('bots.skyline_archive.scanner.asyncio.sleep',new_callable=AsyncMock):
                self.assertEqual(await scanner.visit(url,'module'),ready)
            self.assertEqual(scanner.page.evaluate.await_count,2)

    async def test_module_waits_for_selected_category(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner=Scanner(settings(directory)); url=challenge().url
            early=dict(links=[dict(href=url.removeprefix('https://cyberskyline.com'),title='Synthetic example (Hard)')])
            ready=dict(early,category='Password Cracking')
            scanner.page=SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=200)),
                url=url,evaluate=AsyncMock(side_effect=[early,ready]),
                locator=lambda _:SimpleNamespace(count=AsyncMock(return_value=0)))
            with patch('bots.skyline_archive.scanner.asyncio.sleep',new_callable=AsyncMock):
                self.assertEqual(await scanner.visit(url,'module'),ready)

    async def test_401_signin_and_network_failures_are_distinguished(self):
        from playwright.async_api import TimeoutError as BrowserTimeout
        with tempfile.TemporaryDirectory() as directory:
            scanner=Scanner(settings(directory))
            page=SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=401)))
            scanner.page=page
            with self.assertRaises(SessionExpired): await scanner.visit('https://cyberskyline.com/competition','events')
            scanner.last_visit=0
            page.goto.return_value=SimpleNamespace(status=403)
            with self.assertRaises(ArchiveError) as caught: await scanner.visit('https://cyberskyline.com/competition','events')
            self.assertNotIsInstance(caught.exception,SessionExpired)
            scanner.last_visit=0
            page.goto.side_effect=BrowserTimeout('test timeout')
            with self.assertRaises(ArchiveError) as caught: await scanner.visit('https://cyberskyline.com/competition','events')
            self.assertNotIsInstance(caught.exception,SessionExpired)
            scanner.last_visit=0
            page.goto.side_effect=None
            page.goto.return_value=SimpleNamespace(status=200)
            page.url='https://cyberskyline.com/login'
            with self.assertRaises(SessionExpired): await scanner.visit('https://cyberskyline.com/competition','events')
            scanner.last_visit=0
            page.url='https://status.example.test/maintenance'
            page.locator=lambda _:SimpleNamespace(count=AsyncMock(return_value=0))
            with self.assertRaises(ArchiveError) as caught: await scanner.visit('https://cyberskyline.com/competition','events')
            self.assertNotIsInstance(caught.exception,SessionExpired)

    async def test_invalid_saved_login_stops_before_launching_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            config=settings(directory)
            config.auth_file.write_text('{"cookies":"invalid"}')
            with patch('playwright.async_api.async_playwright') as runtime:
                with self.assertRaises(SessionExpired): await Scanner(config).validate_session()
            runtime.assert_not_called()

    async def test_valid_question_with_password_input_is_not_a_login_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            scanner=Scanner(settings(directory))
            snapshot={'challenge':{'questions':['Question text']}}
            scanner.page=SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=200)),
                url=challenge().url,evaluate=AsyncMock(return_value=snapshot),
                locator=lambda _:SimpleNamespace(count=AsyncMock(return_value=1)))
            self.assertEqual(await scanner.visit(challenge().url,'challenge'),snapshot)


class Identity:
    def __init__(self,ident): self.id=ident


def permission_set(**values):
    names=('view_channel','send_messages','read_message_history','embed_links','attach_files','manage_channels',
           'create_public_threads','send_messages_in_threads','manage_threads')
    return SimpleNamespace(**{**{n:True for n in names},**values})


class FakeMessage:
    def __init__(self,channel,ident,embed=None,content=''):
        self.channel,self.id,self.embeds,self.content=channel,ident,[embed] if embed else [],content
        self.author=SimpleNamespace(id=999,bot=True)
        self.created_at=datetime.now(timezone.utc)
        self.jump_url=f'https://discord.com/channels/123/{channel.id}/{ident}'
        self.edits=0
        self.attachments=[]

    async def edit(self,**kwargs):
        # discord.py returns a new Message; it does not mutate the original instance.
        message=FakeMessage(self.channel,self.id,kwargs.get('embed',self.embeds[0] if self.embeds else None),
                            kwargs.get('content',self.content))
        message.edits=self.edits+1
        message.attachments=kwargs.get('attachments',self.attachments)
        self.channel.messages[self.id]=message
        return message

    async def create_thread(self,**kwargs):
        thread=FakeChannel(self.channel.guild,self.id,kwargs['name'],thread=True)
        self.channel.guild.channels[self.id]=thread
        return thread


class FakeChannel:
    def __init__(self,guild,ident,name,category=None,thread=False):
        self.guild,self.id,self.name,self.category=guild,ident,name,category
        self.messages={}; self.text_channels=[]
        self.archived=False; self.locked=False; self.parent_id=category.id if thread and category else None
        self.permissions=permission_set()
        self.fail_after_send=False

    def permissions_for(self,member): return self.permissions

    async def send(self,content=None,**kwargs):
        ident=self.guild.next_id(); m=FakeMessage(self,ident,kwargs.get('embed'),content or '')
        self.messages[ident]=m
        if self.fail_after_send:
            self.fail_after_send=False
            raise asyncio.TimeoutError()
        return m

    async def fetch_message(self,ident):
        if ident not in self.messages: raise discord.NotFound(SimpleNamespace(status=404,reason='missing'),{'message':'missing','code':10008})
        return self.messages[ident]

    async def history(self,limit=100,after=None,oldest_first=False):
        rows=list(self.messages.values())
        if not oldest_first: rows.reverse()
        for m in rows[:limit]:
            if after is None or m.created_at>after: yield m

    async def edit(self,**kwargs):
        if 'archived' in kwargs: self.archived=kwargs['archived']


class FakeGuild:
    def __init__(self):
        self.id=123; self.counter=1000; self.channels={}; self.categories=[]
        self.default_role=Identity(0); self.me=Identity(999); self.me.guild_permissions=permission_set()
        self.filesize_limit=8*1024*1024

    def next_id(self): self.counter+=1; return self.counter
    def get_channel(self,ident): return self.channels.get(ident)
    def get_member(self,ident): return Identity(ident)
    async def fetch_member(self,ident): return Identity(ident)
    async def fetch_channel(self,ident):
        if ident not in self.channels: raise discord.NotFound(SimpleNamespace(status=404,reason='missing'),{'message':'missing','code':10003})
        return self.channels[ident]
    async def create_category(self,name,**kwargs):
        c=FakeChannel(self,self.next_id(),name); self.categories.append(c); self.channels[c.id]=c; return c
    async def create_text_channel(self,name,category,**kwargs):
        c=FakeChannel(self,self.next_id(),name,category); self.channels[c.id]=c; category.text_channels.append(c); return c


@unittest.skipIf(discord is None,'Install bot requirements for Discord integration fixtures')
class DiscordFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name); self.guild=FakeGuild()
        self.config=settings(self.tmp.name)
        self.client=SimpleNamespace(settings=self.config,user=Identity(999),get_guild=lambda _:self.guild,
                                   get_channel=self.guild.get_channel,fetch_channel=self.guild.fetch_channel)
        self.preferences=Preferences(self.store,self.config)
        self.files=Attachments(self.store)
        self.archive=DiscordArchive(self.client,self.store,self.files,self.preferences)
        self.client.store,self.client.archive=self.store,self.archive

    async def asyncTearDown(self): self.store.close(); self.tmp.cleanup()

    async def test_archive_reuses_category_channel_posts_threads_after_restart(self):
        c=challenge()
        await self.archive.publish([c])
        q=self.store.question(key=self.store.rows('SELECT key FROM questions')[0]['key'])
        thread=self.guild.channels[q['thread_id']]
        discussion=await thread.send('User discussion stays here')
        thread.archived=True
        count=self.guild.counter
        self.store.close(); self.store=Store(self.tmp.name)
        self.archive=DiscordArchive(self.client,self.store,self.files,self.preferences)
        await self.archive.publish([c])
        self.assertEqual(self.guild.counter,count)
        self.assertIn(discussion.id,thread.messages)
        self.assertFalse(thread.archived)
        self.assertEqual(len(self.guild.categories),1)
        self.assertEqual(len(self.guild.categories[0].text_channels),1)
        self.assertEqual(self.guild.categories[0].text_channels[0].name,'passcracking-easy')

    async def test_missing_parent_is_repaired_without_replacing_existing_thread(self):
        c=challenge(); await self.archive.publish([c])
        q=self.store.rows('SELECT * FROM questions')[0]
        self.guild.channels[q['channel_id']].messages.pop(q['message_id'])
        await self.archive.publish([c])
        repaired=self.store.question(key=q['key'])
        self.assertEqual(repaired['thread_id'],q['thread_id'])
        self.assertNotEqual(repaired['message_id'],q['message_id'])

    async def test_changed_question_is_not_overwritten_by_status_fields(self):
        c=challenge(); await self.archive.publish([c])
        q=self.store.rows('SELECT * FROM questions')[0]
        revised=replace(c,questions=('Q1 - 20 points\nRevised complete question text?',))
        await self.archive.publish([revised])
        parent=self.guild.channels[q['channel_id']].messages[q['message_id']]
        self.assertIn('Revised complete question text?',parent.embeds[0].description)
        self.assertEqual(self.store.question(key=q['key'])['thread_id'],q['thread_id'])

    async def test_ambiguous_send_recovers_existing_message_without_duplicate(self):
        channel=await self.guild.create_text_channel('test',await self.guild.create_category('test'))
        channel.fail_after_send=True
        with self.assertRaises(asyncio.TimeoutError): await self.archive.message(channel,'stable','text')
        self.assertEqual(len(channel.messages),1)
        await self.archive.message(channel,'stable','text')
        self.assertEqual(len(channel.messages),1)
        self.assertEqual(self.store.one('SELECT state FROM posts')['state'],'active')

    async def test_pending_send_keeps_original_channel_after_mapping_change(self):
        category=await self.guild.create_category('test')
        old=await self.guild.create_text_channel('old',category)
        new=await self.guild.create_text_channel('new',category)
        old.fail_after_send=True
        with self.assertRaises(asyncio.TimeoutError): await self.archive.message(old,'stable','text')
        await self.archive.message(new,'stable','text')
        self.assertEqual(len(old.messages),1)
        self.assertEqual(len(new.messages),0)

    async def test_long_questions_complete_in_parent_parts_and_thread(self):
        text='Q1 - 25 points\n'+('A long synthetic question. '*400)
        c=challenge(questions=(text,),prompt='Shared instructions. '*300)
        await self.archive.publish([c])
        q=self.store.rows('SELECT * FROM questions')[0]
        for key in ('question/'+q['key'],'thread/'+q['key']):
            rows=self.store.rows('SELECT * FROM posts WHERE key LIKE ? ORDER BY key',(key+'/part%',))
            contents=''.join(self.guild.channels[r['channel_id']].messages[r['message_id']].embeds[0].description for r in rows)
            self.assertIn(text,contents)
        self.assertEqual(q['points'],25)
        before=self.guild.counter
        await self.archive.publish([c])
        self.assertEqual(self.guild.counter,before)

    async def test_upload_failure_can_retry_without_duplicating_successful_upload(self):
        c=challenge(); self.store.upsert_challenge(c)
        path=self.files.root/'sample.bin'; path.write_bytes(b'1234')
        self.store.attachment('f',challenge_key=c.key,name='sample.bin',source=c.url,status='ready',path=str(path),size=4,sha256=hashlib.sha256(b'1234').hexdigest())
        channel=await self.archive.destination(c)
        with patch.object(channel,'send',new=AsyncMock(side_effect=discord.HTTPException(SimpleNamespace(status=500,reason='temporary'),{'message':'temporary'}))):
            links=await self.archive.files(channel,c)
        self.assertIn('upload failed',links[0])
        self.assertEqual(self.store.attachment('f')['status'],'upload-failed')
        self.store.attachment('f',status='ready')  # Successful cached-file revalidation on next scan.
        await self.archive.files(channel,c)
        count=len(channel.messages)
        other=await self.guild.create_text_channel('replacement',channel.category)
        links=await self.archive.files(other,c)
        self.assertEqual(len(channel.messages),count)
        self.assertEqual(len(other.messages),0)
        self.assertEqual(self.store.attachment('f')['status'],'uploaded')
        self.assertEqual(self.store.attachment('f')['channel_id'],channel.id)
        self.assertIn(f'/123/{channel.id}/',links[0])

    async def test_upload_limit_records_failure_and_source_link(self):
        c=challenge(); self.store.upsert_challenge(c)
        path=self.files.root/'sample.bin'; path.write_bytes(b'1234')
        self.store.attachment('f',challenge_key=c.key,name='sample.bin',source=c.url,status='ready',path=str(path),size=4,sha256='x')
        self.guild.filesize_limit=3
        await self.archive.publish([c])
        self.assertEqual(self.store.attachment('f')['status'],'oversized-upload')
        text='\n'.join(m.embeds[0].description for ch in self.guild.channels.values() for m in ch.messages.values() if m.embeds)
        self.assertIn('exceeds this server',text)
        self.assertIn(c.url,text)

    async def test_mappings_change_without_relocating_old_content(self):
        c=challenge(); await self.archive.publish([c])
        q=self.store.rows('SELECT * FROM questions')[0]
        new=await self.guild.create_text_channel('new',await self.guild.create_category('new'))
        self.store.map('channel','password cracking/easy',new.id)
        await self.archive.publish([c])
        self.assertEqual(self.store.question(key=q['key'])['channel_id'],q['channel_id'])

    async def test_settings_persist_validate_and_use_environment_defaults(self):
        ch=await self.guild.create_text_channel('hub',await self.guild.create_category('hub'))
        await self.preferences.save(dict(archive_hub=ch.id,archive_enabled=True,frequency=120,enabled=True,default_preview=True),self.guild)
        self.assertTrue(Preferences(self.store,self.config).effective()['default_preview'])
        with self.assertRaises(ArchiveError): await self.preferences.save(dict(frequency=1),self.guild)
        self.assertEqual(self.preferences.effective()['frequency'],120)
        ch.permissions=permission_set(send_messages=False)
        with self.assertRaises(ArchiveError): await self.preferences.save(dict(notification_channel=ch.id),self.guild)
        self.assertEqual(self.preferences.effective()['notification_channel'],0)
        self.store.close(); self.store=Store(self.tmp.name)
        self.assertEqual(Preferences(self.store,self.config).effective()['frequency'],120)

    async def test_ten_minute_frequency_persists_and_rejects_invalid_changes(self):
        await self.preferences.save(dict(frequency=10),self.guild)
        for invalid in (0,9,10081,True,10.5,'10'):
            with self.subTest(invalid=invalid), self.assertRaises(ArchiveError):
                await self.preferences.save(dict(frequency=invalid),self.guild)
            self.assertEqual(self.preferences.effective()['frequency'],10)
        self.store.close(); self.store=Store(self.tmp.name)
        self.assertEqual(Preferences(self.store,self.config).effective()['frequency'],10)

    async def test_picker_paginates_over_discord_limits(self):
        catalog=[dict(season=f'fall-{2000+i}',competition='gym',event_url=f'event{i}',event=f'Event {i}',category='Forensics',level='easy') for i in range(60)]
        picker=Picker(self.client,456,catalog)
        self.assertEqual(len(picker.children[0].options),25)
        picker.page=2; picker.build()
        self.assertEqual(len(picker.children[0].options),13)
        self.assertTrue(picker.children[2].disabled)

    async def test_search_hides_channel_content(self):
        await self.archive.publish([challenge()])
        q=self.store.rows('SELECT * FROM questions')[0]
        self.guild.channels[q['channel_id']].permissions=permission_set(view_channel=False)
        view=SearchView(self.client,456,'example',{})
        content=await view.render(Identity(456))
        self.assertNotIn('Synthetic example',content)
        self.assertIn('No matching questions',content)

    async def test_picker_filters_source_scope_and_rejects_other_users(self):
        row=dict(season='spring-2026',competition='gym',event_url='one',event='NCL Spring 2026 Gym',category='Forensics',level='easy')
        self.assertTrue(matches(row,dict(season='spring-2026',category='forensics',level='easy')))
        self.assertFalse(matches(row,dict(event_url='two')))
        picker=Picker(self.client,456,[row])
        interaction=SimpleNamespace(guild_id=123,user=Identity(789),response=SimpleNamespace(send_message=AsyncMock()))
        self.assertFalse(await picker.interaction_check(interaction))
        interaction.response.send_message.assert_awaited_once()


@unittest.skipIf(discord is None,'Install bot requirements for workflow fixtures')
class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.bot=SkylineBot(settings(self.tmp.name))

    async def asyncTearDown(self): await self.bot.close(); self.tmp.cleanup()

    async def test_preview_does_not_archive_download_or_mark_synced(self):
        c=challenge(attachment_refs=(AttachmentRef('a.txt','https://cyberskyline.com/artifact/a'),))
        async def collect(*args,**kwargs):
            await kwargs['on_challenge'](c,None)
            return ScanResult(challenges=[c])
        with patch('bots.skyline_archive.bot.Scanner') as scanner,patch('bots.skyline_archive.bot.GitHub') as github,patch.object(self.bot.archive,'publish',new=AsyncMock()) as publish,patch.object(self.bot.attachments,'fetch',new=AsyncMock()) as fetch:
            scanner.return_value.collect=AsyncMock(side_effect=collect)
            self.bot.start_sync(all_events=True,preview=True)
            await self.bot.scan_task
            fetch.assert_not_awaited(); publish.assert_not_awaited(); github.assert_not_called()
        self.assertEqual(self.bot.store.rows('SELECT * FROM questions'),[])
        self.assertEqual(self.bot.store.rows('SELECT * FROM attachments'),[])
        self.assertIn('Preview complete',self.bot.archive_status)

    async def test_expired_login_alerts_once_and_blocks_new_attempts(self):
        destination=SimpleNamespace(send=AsyncMock())
        with patch.object(self.bot.archive,'channel',new=AsyncMock(return_value=destination)):
            await self.bot.session_expired('expired',42)
            await self.bot.session_expired('expired',42)
        destination.send.assert_awaited_once()
        with self.assertRaisesRegex(ArchiveError,'Waiting for login'): self.bot.start_sync(all_events=True)
        self.assertTrue(self.bot.store.get('auth_invalid'))
        self.assertTrue(self.bot.store.get('auth_alert_sent'))

    async def test_network_error_does_not_mark_login_invalid(self):
        with patch('bots.skyline_archive.bot.Scanner') as scanner:
            scanner.return_value.collect=AsyncMock(side_effect=ArchiveError('Network timeout'))
            self.bot.start_sync(all_events=True,preview=True)
            await self.bot.scan_task
        self.assertFalse(self.bot.store.get('auth_invalid',False))

    async def test_session_recheck_unblocks_scans(self):
        self.bot.store.put('auth_invalid',True)
        self.bot.store.put('auth_alert_sent',True)
        interaction=SimpleNamespace(channel_id=42,response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
        commands=SessionCommands(self.bot)
        with patch('bots.skyline_archive.bot.Scanner') as scanner:
            scanner.return_value.validate_session=AsyncMock(return_value=True)
            await commands.get_command('recheck').callback(commands,interaction)
        self.assertFalse(self.bot.store.get('auth_invalid'))
        self.assertFalse(self.bot.store.get('auth_alert_sent'))

    async def test_manual_and_scheduled_work_cannot_overlap(self):
        entered=asyncio.Event()
        async def collect(*a,**k): entered.set(); await asyncio.Event().wait()
        with patch('bots.skyline_archive.bot.Scanner') as scanner:
            scanner.return_value.collect=AsyncMock(side_effect=collect)
            self.bot.start_sync(all_events=True,preview=True)
            await asyncio.wait_for(entered.wait(),3)
            with self.assertRaisesRegex(ArchiveError,'already running'): self.bot.start_sync(all_events=True)
            self.bot.stop_sync()
            await asyncio.gather(self.bot.scan_task,return_exceptions=True)

    async def test_verification_records_exact_answer_and_updates_same_thread_and_parent(self):
        guild=FakeGuild()
        client=SimpleNamespace(settings=self.bot.settings,user=Identity(999),get_guild=lambda _:guild,
                               get_channel=guild.get_channel,fetch_channel=guild.fetch_channel)
        self.bot.archive=DiscordArchive(client,self.bot.store,self.bot.attachments,self.bot.preferences)
        c=challenge(questions=('What is the decoded hex value?',),prompt='Encoded input: `20412020420a`')
        await self.bot.archive.publish([c])
        q=self.bot.store.question(key=self.bot.store.rows('SELECT key FROM questions')[0]['key'])
        thread=guild.channels[q['thread_id']]
        interaction=SimpleNamespace(channel=thread,channel_id=thread.id,guild_id=123,user=Identity(456),
            response=SimpleNamespace(defer=AsyncMock(),is_done=lambda:False),followup=SimpleNamespace(send=AsyncMock()))
        await self.bot.verify_answer(interaction,q,' A  B\n')
        record=self.bot.store.latest_verification(q['key'])
        self.assertEqual(record['answer'],' A  B\n')
        self.assertEqual(record['user_id'],456)
        self.assertEqual(record['outcome'],'Verified correct')
        self.assertIn('" A  B\\n"',list(thread.messages.values())[-1].content)
        parent=guild.channels[q['channel_id']].messages[q['message_id']]
        self.assertIn('Verified correct',[f.value for f in parent.embeds[0].fields if f.name=='Latest verification'][0])
        await self.bot.archive.publish([c])
        self.assertEqual(self.bot.store.latest_verification(q['key'])['id'],record['id'])

    async def test_long_ai_report_is_saved_and_attached_without_silent_truncation(self):
        guild=FakeGuild()
        client=SimpleNamespace(settings=self.bot.settings,user=Identity(999),get_guild=lambda _:guild,
                               get_channel=guild.get_channel,fetch_channel=guild.fetch_channel)
        self.bot.archive=DiscordArchive(client,self.bot.store,self.bot.attachments,self.bot.preferences)
        await self.bot.archive.publish([challenge()])
        q=self.bot.store.question(key=self.bot.store.rows('SELECT key FROM questions')[0]['key'])
        thread=guild.channels[q['thread_id']]
        interaction=SimpleNamespace(channel=thread,channel_id=thread.id,guild_id=123,user=Identity(456),
            response=SimpleNamespace(defer=AsyncMock(),is_done=lambda:False),followup=SimpleNamespace(send=AsyncMock()))
        details='Synthetic evidence. '*250
        self.bot.verifier.check=AsyncMock(return_value=dict(outcome='Inconclusive',method='OpenAI assisted',evidence=details))
        await self.bot.verify_answer(interaction,q,' Candidate\n')
        self.assertEqual(self.bot.store.latest_verification(q['key'])['evidence'],details)
        message=list(thread.messages.values())[-1]
        self.assertLess(len(message.content),2000)
        self.assertEqual(message.attachments[-1].filename,'verification-report.txt')

    async def test_scheduler_uses_saved_preferences_and_respects_auth_block(self):
        self.bot.store.save_settings(dict(enabled=True,frequency=120,notification_channel=42,default_preview=True))
        self.bot.recovered.set()
        for invalid in (False,True):
            self.bot.store.put('auth_invalid',invalid)
            self.bot.store.put('last_scheduled',0)
            with (patch.object(self.bot,'wait_until_ready',new=AsyncMock()),
                  patch.object(self.bot,'is_closed',side_effect=[False,True]),
                  patch.object(self.bot.archive,'channel',new=AsyncMock(return_value=Identity(42))),
                  patch('bots.skyline_archive.bot.asyncio.sleep',new=AsyncMock()),
                  patch.object(self.bot,'start_sync') as start):
                await self.bot.schedule_loop()
                if invalid:
                    start.assert_not_called()
                else:
                    start.assert_called_once()
                    self.assertTrue(start.call_args.kwargs['all_events'])
                    self.assertGreater(self.bot.store.get('last_scheduled'),0)

    async def test_ten_minute_schedule_waits_until_due_and_does_not_overlap(self):
        event='https://cyberskyline.com/world/'+'1'*24
        self.bot.settings.event_url=event
        self.bot.store.save_settings(dict(enabled=True,frequency=10,notification_channel=42,default_preview=False))
        self.bot.recovered.set()
        for elapsed,busy,expected in ((599,False,False),(600,True,False),(600,False,True)):
            with self.subTest(elapsed=elapsed,busy=busy):
                self.bot.store.put('last_scheduled',1000)
                with (patch.object(self.bot,'wait_until_ready',new=AsyncMock()),
                      patch.object(self.bot,'is_closed',side_effect=[False,True]),
                      patch.object(self.bot,'busy',return_value=busy),
                      patch.object(self.bot.archive,'channel',new=AsyncMock(return_value=Identity(42))),
                      patch('bots.skyline_archive.bot.asyncio.sleep',new=AsyncMock()),
                      patch('bots.skyline_archive.bot.time.time',return_value=1000+elapsed),
                      patch.object(self.bot,'start_sync') as start):
                    await self.bot.schedule_loop()
                    if expected:
                        start.assert_called_once()
                        self.assertEqual(start.call_args.args,(event,))
                        self.assertFalse(start.call_args.kwargs['all_events'])
                        self.assertEqual(self.bot.store.get('last_scheduled'),1600)
                    else:
                        start.assert_not_called()
                        self.assertEqual(self.bot.store.get('last_scheduled'),1000)


if __name__=='__main__': unittest.main()
