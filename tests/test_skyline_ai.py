"""Synthetic metadata and mocked OpenAI tests: no network, Discord or competition artifacts."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import zlib

from tools import image_metadata
from bots.skyline_archive.ai_verification import AIError, OpenAIAssistant, sanitize
from bots.skyline_archive.attachments import Attachments
from bots.skyline_archive.core import ArchiveError, Challenge
from bots.skyline_archive.preferences import Preferences
from bots.skyline_archive.settings import Settings
from bots.skyline_archive.storage import Store
from bots.skyline_archive.verification import Verifier
from bots.skyline_archive.verify_worker import check, inspect_evidence


def tiff(values=None, endian='<'):
    values = values or [(0x9003, '2001:02:03 04:05:59'), (0x9004, '2001:02:03 04:05:59')]
    pack = lambda f,*args: struct.pack(endian+f,*args)
    header = (b'II' if endian == '<' else b'MM') + pack('HI',42,8)
    first = pack('H',1)+pack('HHII',0x8769,4,1,26)+pack('I',0)
    start = 26 + 2 + len(values)*12 + 4
    entries, body = b'', b''
    for tag, value in values:
        raw = value.encode('ascii')+b'\0'
        entries += pack('HHII',tag,2,len(raw),start+len(body))
        body += raw
    return header+first+pack('H',len(values))+entries+pack('I',0)+body


def jpeg(values=None):
    block = b'Exif\0\0' + tiff(values)
    return b'\xff\xd8\xff\xe1' + struct.pack('>H',len(block)+2)+block+b'\xff\xd9'


def final_response(**values):
    assessment = dict(assessment='uncertain', suggested_answer=None,
                      explanation='More evidence is needed.', evidence_ids=[], next_step='Inspect the original file.')
    assessment.update(values)
    return dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(assessment))])])


def tool_response(operation='metadata',file_id=0,name='inspect_evidence'):
    return dict(status='completed',output=[dict(type='reasoning',id='reasoning-fixture',encrypted_content='opaque'),
        dict(type='function_call',name=name,call_id='call-fixture',arguments=json.dumps(dict(file_id=file_id,operation=operation)))])


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self, data=None, question=None, proposed='2001-02-03 04:05'):
        raw=jpeg() if data is None else data
        path=self.root/'fixture.jpg'; path.write_bytes(raw)
        return dict(files=[dict(name='fixture.jpg',path=str(path),sha256=hashlib.sha256(raw).hexdigest())],
                    root=str(self.root),instructions='',answer=proposed,
                    question=question or 'Q1 - 10 points\nWhen was the image created? Round down to the nearest minute')

    def test_creation_timestamp_rounds_down_and_reports_mismatch(self):
        value=self.payload()
        self.assertEqual(check(value)['outcome'],'Verified correct')
        self.assertIn('byte',check(value)['evidence'])
        self.assertEqual(check({**value,'answer':'2001-02-03 04:06'})['outcome'],'Verified incorrect')
        self.assertEqual(check({**value,'answer':' 2001-02-03 04:05 '})['outcome'],'Inconclusive')

    def test_both_byte_orders_and_original_offsets(self):
        for endian in ('<','>'):
            raw=tiff(endian=endian); report=image_metadata.inspect(raw)
            self.assertEqual(report['format'],'TIFF')
            for tag in report['tags']:
                self.assertTrue(raw[tag['offset']:].startswith(tag['value'].encode()))

    def test_conflicting_creation_times_never_choose_convenient_tag(self):
        value=self.payload(jpeg([(0x9003,'2001:02:03 04:05:59'),(0x9004,'2002:02:03 04:05:59')]))
        self.assertEqual(check(value)['outcome'],'Inconclusive')

    def test_modification_time_is_not_creation(self):
        value=self.payload(jpeg([(0x0132,'2001:02:03 04:05:59')]))
        self.assertEqual(check(value)['outcome'],'Inconclusive')

    def test_derived_or_timezone_questions_are_not_automatically_verified(self):
        for question in ('When was the image created in UTC?', 'When was the image modified?',
                         'What date is one day after the image was created?'):
            self.assertEqual(check(self.payload(question=question))['outcome'],'Inconclusive')

    def test_png_exif_checksum_and_missing_metadata(self):
        def chunk(kind,data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        raw=b'\x89PNG\r\n\x1a\n'+chunk(b'eXIf',tiff())+chunk(b'IEND',b'')
        self.assertEqual(image_metadata.inspect(raw)['exif_blocks'],1)
        broken=bytearray(raw); broken[30]^=1
        with self.assertRaises(ValueError): image_metadata.inspect(bytes(broken))
        self.assertEqual(image_metadata.inspect(b'\xff\xd8\xff\xd9')['tags'],[])

    def test_malformed_offsets_truncation_and_directory_cycles(self):
        for raw in (b'II',b'\xff\xd8\xff\xe1\xff\xff',tiff()[:50]):
            with self.assertRaises(ValueError): image_metadata.inspect(raw)
        raw=bytearray(tiff()); struct.pack_into('<I',raw,18,8)
        with self.assertRaises(ValueError): image_metadata.inspect(raw)

    def test_tool_cannot_read_unlisted_or_changed_files(self):
        value=self.payload()
        with self.assertRaises(ValueError): inspect_evidence({**value,'inspect':dict(file_id=-1,operation='text')})
        with self.assertRaises(ValueError): inspect_evidence({**value,'inspect':dict(file_id=0,operation='shell')})
        Path(value['files'][0]['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError): inspect_evidence({**value,'inspect':dict(file_id=0,operation='text')})

    def test_tool_reports_partial_text_coverage(self):
        value=self.payload(b'x'*9000)
        report=inspect_evidence({**value,'inspect':dict(file_id=0,operation='text')})
        self.assertTrue(report['truncated']); self.assertEqual(len(report['text']),8192)

    def test_ai_cannot_select_ambiguous_file_to_force_a_verdict(self):
        value=self.payload()
        second={**value['files'][0],'name':'other.jpg'}
        value['files'].append(second)
        self.assertIn('error',inspect_evidence({**value,'inspect':dict(file_id=0,operation='verify')}))


class AITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name)
        self.settings=SimpleNamespace(openai_api_key='fixture-api-key',openai_model='gpt-5.4-mini',ai_daily_requests=40,
                                      ai_output_tokens=1600,ai_timeout=120,discord_token='fixture-discord-secret',github_token='fixture-github-secret')
        self.local=dict(outcome='Inconclusive',method='fixture',evidence='No direct check.')
        self.payload=dict(question='What does the evidence show?',instructions='Use the original.',answer=' A \n',
                          files=[dict(name='fixture.jpg',path='/private/do-not-send',sha256='private-digest')],
                          root='/private/do-not-send',unavailable_files=[])

    async def asyncTearDown(self):
        self.store.close(); self.tmp.cleanup()

    async def run_ai(self,responses,tool=None):
        request=AsyncMock(side_effect=responses)
        ai=OpenAIAssistant(self.store,self.settings,request=request)
        tool=tool or AsyncMock(return_value=dict(tags=[]))
        value=await ai.assist(self.payload,self.local,tool)
        return value,request,tool

    async def test_stateless_tool_replay_and_opinion_never_becomes_verified(self):
        value,request,tool=await self.run_ai([tool_response(),final_response(assessment='supported',explanation='The tag supports this candidate.',evidence_ids=['E1'])])
        self.assertEqual(value['outcome'],'Inconclusive')
        self.assertIn('not independent proof',value['evidence'])
        second=request.call_args.args[0]
        self.assertFalse(second['store'])
        self.assertIn('reasoning',[x.get('type') for x in second['input']])
        self.assertIn('function_call_output',[x.get('type') for x in second['input']])
        self.assertEqual(tool.call_args.args[0],dict(file_id=0,operation='metadata'))
        sent=json.dumps(request.call_args_list)
        self.assertNotIn('/private/do-not-send',sent)

    async def test_exact_proposed_answer_and_missing_artifact_status_are_passed(self):
        self.payload['unavailable_files']=[dict(name='large.bin',status='oversized')]
        _,request,_=await self.run_ai([final_response()])
        context=json.loads(request.call_args.args[0]['input'][0]['content'])
        self.assertEqual(context['proposed_answer'],' A \n')
        self.assertEqual(context['unavailable_files'][0]['status'],'oversized')

    async def test_only_actual_local_verify_result_can_be_correct(self):
        proof=dict(outcome='Verified correct',method='fixture local check',evidence='Measured original bytes.')
        value,_,_=await self.run_ai([tool_response('verify')],AsyncMock(return_value=proof))
        self.assertEqual(value['outcome'],'Verified correct')
        self.assertEqual(value['method'],'AI selected · fixture local check')

    async def test_missing_key_and_disabled_budget_make_no_requests(self):
        self.settings.openai_api_key=''
        value,request,_=await self.run_ai([])
        self.assertEqual(value['outcome'],'Inconclusive'); request.assert_not_called()
        self.settings.openai_api_key='fixture'; self.settings.ai_daily_requests=0
        value,request,_=await self.run_ai([])
        self.assertEqual(value['outcome'],'Verification error'); request.assert_not_called()

    async def test_daily_attempt_budget_persists_across_restart(self):
        self.settings.ai_daily_requests=1
        await self.run_ai([final_response()])
        self.store.close(); self.store=Store(self.tmp.name)
        value,request,_=await self.run_ai([])
        self.assertIn('daily AI request limit',value['evidence']); request.assert_not_called()

    async def test_invalid_calls_and_fabricated_evidence_are_rejected(self):
        for response in (tool_response(name='shell'),tool_response(file_id=-1),tool_response(operation='eval'),
                         final_response(evidence_ids=['fake']),final_response(outcome='Verified correct')):
            value,_,tool=await self.run_ai([response])
            self.assertEqual(value['outcome'],'Verification error'); tool.assert_not_called()

    async def test_provider_and_tool_errors_are_not_incorrect_answers(self):
        value,_,_=await self.run_ai([AIError('Provider unavailable.')])
        self.assertEqual(value['outcome'],'Verification error')
        value,_,_=await self.run_ai([tool_response()],AsyncMock(return_value=dict(outcome='Verification error',method='worker',evidence='File failed.')))
        self.assertEqual(value['outcome'],'Verification error')

    async def test_overall_timeout_returns_error(self):
        value,_,_=await self.run_ai([asyncio.TimeoutError()])
        self.assertEqual(value['outcome'],'Verification error')
        self.assertIn('time limit',value['evidence'])

    async def test_http_auth_error_hides_provider_body_and_disables_redirects(self):
        try:
            import aiohttp
        except ImportError:
            self.skipTest('Optional bot dependencies not installed')
        class Context:
            def __init__(self,value): self.value=value
            async def __aenter__(self): return self.value
            async def __aexit__(self,*args): return False
        from unittest.mock import Mock
        response=SimpleNamespace(status=401)
        session=SimpleNamespace(post=Mock(return_value=Context(response)))
        ai=OpenAIAssistant(self.store,self.settings)
        with patch.object(aiohttp,'ClientSession',return_value=Context(session)):
            value=await ai.assist(self.payload,self.local,AsyncMock())
        self.assertEqual(value['outcome'],'Verification error')
        self.assertNotIn(self.settings.openai_api_key,value['evidence'])
        self.assertEqual(session.post.call_args.args[0],'https://api.openai.com/v1/responses')
        self.assertFalse(session.post.call_args.kwargs['allow_redirects'])

    async def test_successful_http_reads_response_in_chunks(self):
        try:
            import aiohttp
        except ImportError:
            self.skipTest('Optional bot dependencies not installed')
        class Context:
            def __init__(self,value): self.value=value
            async def __aenter__(self): return self.value
            async def __aexit__(self,*args): return False
        async def chunks(size):
            raw=json.dumps(final_response()).encode()
            for start in range(0,len(raw),13): yield raw[start:start+13]
        from unittest.mock import Mock
        response=SimpleNamespace(status=200,content=SimpleNamespace(iter_chunked=chunks))
        session=SimpleNamespace(post=Mock(return_value=Context(response)))
        ai=OpenAIAssistant(self.store,self.settings)
        with patch.object(aiohttp,'ClientSession',return_value=Context(session)):
            value=await ai.assist(self.payload,self.local,AsyncMock())
        self.assertEqual(value['outcome'],'Inconclusive')

    async def test_incomplete_response_and_bad_json_fail_closed(self):
        for response in (dict(status='incomplete',output=[]),dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text='nonsense')])])):
            value,_,_=await self.run_ai([response]); self.assertEqual(value['outcome'],'Verification error')

    async def test_refusal_and_no_evidence_remain_inconclusive(self):
        response=dict(status='completed',output=[dict(type='message',content=[dict(type='refusal',refusal='No')])])
        value,_,_=await self.run_ai([response]); self.assertEqual(value['outcome'],'Inconclusive')
        value,_,_=await self.run_ai([final_response(assessment='supported')])
        self.assertIn('uncertain',value['evidence'])

    async def test_context_limits_and_tool_step_limit(self):
        value,request,_=await self.run_ai([tool_response()]*4)
        self.assertEqual(value['outcome'],'Verification error'); self.assertEqual(request.await_count,4)
        self.payload['instructions']='x'*30000
        value,request,_=await self.run_ai([]); request.assert_not_called()

    async def test_sensitive_values_and_headers_are_redacted_without_breaking_json(self):
        text='Authorization: Bearer fixture-discord-secret\nURL https://example.test/?token=secret\nend'
        result=sanitize(dict(text=text,key='fixture-api-key'),('fixture-api-key','fixture-discord-secret'))
        self.assertNotIn('fixture-',json.dumps(result)); self.assertNotIn('token=secret',json.dumps(result))
        self.assertIn('end',result['text'])

    async def test_worker_is_offline_and_ai_runs_only_for_inconclusive_when_enabled(self):
        files=Attachments(self.store)
        challenge=Challenge(url='https://cyberskyline.com/module/'+'1'*24+'/'+ '2'*24+'/'+ '3'*24,
            event='NCL Spring 2026 Gym',category='Forensics',title='Synthetic (Easy)',prompt='',questions=('What is the value?',),question_ids=('q1',))
        row=self.store.upsert_challenge(challenge)[0]
        question=self.store.question(key=row['key'])
        ai=SimpleNamespace(assist=AsyncMock(return_value=self.local))
        verifier=Verifier(self.store,files,ai=ai,ai_enabled=lambda:False)
        await verifier.check(question,'candidate'); ai.assist.assert_not_called()
        verifier.ai_enabled=lambda:True
        await verifier.check(question,'candidate'); ai.assist.assert_awaited_once()
        ai.assist.reset_mock()
        question={**question,'text':'What is the decoded hex value?','prompt':'Encoded `4142`'}
        self.assertEqual((await verifier.check(question,'AB'))['outcome'],'Verified correct')
        ai.assist.assert_not_called()

    async def test_settings_validate_and_hide_key_and_persist_toggle(self):
        config=Settings.from_env(dict(OPENAI_API_KEY='fixture-api-key'),require_bot=False,require_github=False)
        self.assertNotIn('fixture-api-key',repr(config))
        for override in (dict(AI_MAX_DAILY_REQUESTS='-1'),dict(OPENAI_MODEL='https://example.test'),dict(AI_VERIFY_ENABLED='maybe')):
            with self.assertRaises(ArchiveError): Settings.from_env(override,require_bot=False,require_github=False)
        preferences=Preferences(self.store,config)
        await preferences.save(dict(ai_enabled=True),None)
        self.store.close(); self.store=Store(self.tmp.name)
        self.assertTrue(Preferences(self.store,config).effective()['ai_enabled'])
        with self.assertRaises(ArchiveError):
            await Preferences(self.store,replace(config,openai_api_key='')).save(dict(ai_enabled=True),None)


if __name__=='__main__':
    unittest.main()
