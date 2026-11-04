"""Offline recovery tests; synthetic messages never touch live Discord."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from bots.skyline_archive.core import Challenge
from bots.skyline_archive.storage import Store

try:
    from bots.skyline_archive.discord_archive import marker
except ModuleNotFoundError:
    marker = None

spec = importlib.util.spec_from_file_location('host_recovery', Path(__file__).resolve().parents[1] / 'deploy/pebblehost/recover.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


@unittest.skipUnless(marker, 'Discord dependency required')
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.challenge = Challenge('https://cyberskyline.com/module/' + '/'.join(['1'*24, '2'*24, '3'*24]),
            'NCL Spring 2026 Gymnasium', 'Forensics', 'Fixture (Easy)', 'Synthetic instructions.', ('Q1 - 10 points\nExample?',))
        self.question = self.store.upsert_challenge(self.challenge)[0]

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def message(self, ident=100, author=10, key='fixture/part0', content=''):
        return NS(id=ident, author=NS(id=author), channel=NS(id=20), content=content,
            created_at=datetime(2001, 1, 1, tzinfo=timezone.utc),
            embeds=[NS(footer=NS(text=marker(key)), description='Full synthetic text')])

    def test_only_bot_markers_accepted_and_duplicates_rejected(self):
        a = self.message()
        forged = self.message(101, author=99)
        self.assertEqual(len(recovery.unique_messages([a, forged], 10)), 1)
        with self.assertRaises(ValueError):
            recovery.unique_messages([a, self.message(102)], 10)

    def test_source_ids_recover_to_stable_legacy_keys_and_survive_restart(self):
        a = self.message(key='question/live-id/part0')
        markers = recovery.unique_messages([a], 10)
        recovery.recover_parts(self.store, 'question/legacy-id', markers, source_key='question/live-id')
        recovery.recover_parts(self.store, 'question/legacy-id', markers, source_key='question/live-id')
        self.store.close()
        self.store = Store(self.tmp.name)
        row = self.store.one('SELECT * FROM posts')
        self.assertEqual(row['key'], 'question/legacy-id/part0')
        self.assertEqual(row['message_id'], 100)
        self.assertEqual(self.store.one('SELECT count(*) AS n FROM posts')['n'], 1)

    def test_gaps_missing_posts_and_conflicting_ids_fail(self):
        with self.assertRaises(ValueError):
            recovery.recover_parts(self.store, 'missing', {})
        a = self.message(key='fixture/part1')
        with self.assertRaises(ValueError):
            recovery.recover_parts(self.store, 'fixture', recovery.unique_messages([a], 10))
        recovery.record_post(self.store, 'fixture', self.message())
        with self.assertRaises(ValueError):
            recovery.record_post(self.store, 'fixture', self.message(101))

    def test_legacy_markers_supported_but_two_parent_identities_rejected(self):
        legacy = self.message(key='question/legacy/part0')
        live = self.message(101, key='question/live/part0')
        recovery.recover_parts(self.store, 'question/legacy', recovery.unique_messages([legacy], 10), source_key='question/live')
        with self.assertRaises(ValueError):
            recovery.recover_parts(self.store, 'question/legacy', recovery.unique_messages([legacy, live], 10), source_key='question/live')

    def test_exact_answer_unknown_submitter_and_idempotent_verification(self):
        content = '**Inconclusive — Q1**\n```json\n" Space\\nCase! "\n```\n**Method:** fixture\\_reader\nNo proof.\nNo answer was submitted to Cyber Skyline.'
        a = self.message(content=content)
        self.assertEqual(recovery.restore_verifications(self.store, self.question['key'], [a], 10), 1)
        self.assertEqual(recovery.restore_verifications(self.store, self.question['key'], [a], 10), 0)
        row = self.store.latest_verification(self.question['key'])
        self.assertEqual(row['answer'], ' Space\nCase! ')
        self.assertEqual(row['user_id'], 0)
        self.assertEqual(row['method'], 'fixture_reader')
        self.assertEqual(row['created'], a.created_at.isoformat())

    def test_user_results_and_invalid_json_not_imported(self):
        a = self.message(author=99, content='**Verified correct — Q1**\n```json\n"example"\n```\n**Method:** fixture\nProof.\nNo answer was submitted to Cyber Skyline.')
        b = self.message(content=a.content.replace('"example"', 'invalid'))
        self.assertEqual(recovery.restore_verifications(self.store, self.question['key'], [a,b], 10), 0)

    def test_discord_image_transform_keeps_original_evidence_separate(self):
        row = dict(name='fixture.jpg', size=2048)
        self.assertIsNone(recovery.upload_note(row, NS(attachments=[NS(filename='fixture.jpg', size=2048)])))
        note = recovery.upload_note(row, NS(attachments=[NS(filename='fixture.jpg', size=1024)]))
        self.assertIn('cached original', note)

    def test_missing_or_unrelated_upload_fails_closed(self):
        row = dict(name='fixture.jpg', size=2048)
        for attachments in ([], [NS(filename='other.jpg', size=2048)]):
            with self.assertRaises(recovery.RecoveryError):
                recovery.upload_note(row, NS(attachments=attachments))
