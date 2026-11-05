"""Synthetic fixtures for archive identity, publication, configuration, and watchers."""

import base64
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from bots.skyline_archive.core import (
    ArchiveError, Challenge, ROOT, MANIFEST, INDEX, MODULE, CHALLENGE, archive_files, clean, event_location, level_and_title,
    git_blob_sha, parse_manifest, skyline_url, slug,
)
from bots.skyline_archive.github import ApiError, GitHub
from bots.skyline_archive.scanner import links_for
from bots.skyline_archive.settings import Settings
from bots.skyline_archive.survey import SurveyManager, form_url, is_ready


WORLD_ID, MODULE_ID, CHALLENGE_ID = "1" * 24, "2" * 24, "3" * 24
EVENT = f"https://cyberskyline.com/world/{WORLD_ID}"
SOURCE = f"https://cyberskyline.com/module/{WORLD_ID}/{MODULE_ID}/{CHALLENGE_ID}"


def sample(**kwargs):
    values = dict(url=SOURCE, event="NCL Spring 2026 Practice Game", category="Network Traffic Analysis", title="A synthetic challenge (Easy)",
                  prompt="Read the supplied example capture.", questions=("Q1 - 10 points\nWhich protocol is shown?",))
    values.update(kwargs)
    return Challenge(**values)


def config(**kwargs):
    env = {"DISCORD_BOT_TOKEN": "synthetic", "GITHUB_TOKEN": "synthetic", "DISCORD_GUILD_ID": "123",
           "DISCORD_OWNER_IDS": "456", "SKYLINE_STATE_DIR": str(Path(tempfile.gettempdir()) / "skyline-unit-state")}
    env.update(kwargs)
    return Settings.from_env(env)


class ArchiveTests(unittest.TestCase):
    def test_requested_hierarchy_and_separate_question_files(self):
        item = sample(category="Forensics", title="Metadata (Easy)", questions=("First question?", "Second question?"))
        files = archive_files([item])
        first = "challenges/spring-2026/practice-game/forensics/easy/metadata-q1.md"
        second = "challenges/spring-2026/practice-game/forensics/easy/metadata-q2.md"
        self.assertIn(first, files)
        self.assertIn(second, files)
        self.assertIn("First question?", files[first])
        self.assertNotIn("Second question?", files[first])
        self.assertIn("Second question?", files[second])
        self.assertNotIn("First question?", files[second])
        self.assertIn(item.prompt, files[first])
        self.assertIn(item.prompt, files[second])

    def test_seasons_competitions_and_levels(self):
        for title, expected in (("Gymnasium", "gym"), ("Practice Game", "practice-game"),
                                ("Individual Game", "individual"), ("Team Game", "team-game")):
            self.assertEqual(event_location("NCL Fall 2026 " + title), ("fall-2026", expected))
        self.assertEqual(level_and_title("Example (Hard)"), ("hard", "Example"))
        self.assertEqual(level_and_title("Example"), ("unrated", "Example"))
        self.assertIn("/web/", sample(category="Web Application Exploitation").path_for(1))
        with self.assertRaises(ArchiveError):
            event_location("First Byte")

    def test_removed_source_question_requires_reconciliation(self):
        item = sample(questions=("First question?", "Second question?"))
        previous = parse_manifest(archive_files([item])[MANIFEST])
        with self.assertRaises(ArchiveError):
            archive_files([sample()], previous)

    def test_url_validation(self):
        self.assertEqual(skyline_url(EVENT + "/"), EVENT)
        self.assertEqual(skyline_url(SOURCE, "challenge"), SOURCE)
        for url in ("http://cyberskyline.com/world/" + WORLD_ID, EVENT + "?token=sample",
                    EVENT + "#fragment", EVENT.replace("cyberskyline.com", "cyberskyline.com.evil.example"),
                    EVENT.replace("https://", "https://user@"), "https://127.0.0.1/world/" + WORLD_ID,
                    EVENT + "/../../login", "https://cyberskyline.com:444/world/" + WORLD_ID):
            with self.subTest(url=url), self.assertRaises(ArchiveError):
                skyline_url(url)

    def test_categories_and_slug_collisions_have_distinct_ids(self):
        first = sample(title="A/B")
        second = sample(title="A B", url=SOURCE[:-1] + "4")
        self.assertEqual(slug(first.title), slug(second.title))
        self.assertEqual(first.path_for(1), second.path_for(1))
        files = archive_files([first, second])
        paths = [name for name in files if name.endswith("-q1.md")]
        self.assertEqual(len(paths), 2)
        self.assertIn("/network-traffic-analysis/", first.path_for(1))

    def test_rendering_and_index_are_deterministic(self):
        files = archive_files([sample()])
        previous = parse_manifest(files[MANIFEST])
        self.assertEqual(files, archive_files([sample()], previous))
        self.assertIn("## Question 1", files[sample().path_for(1)])

    def test_manifest_merge_preserves_unseen_challenges(self):
        first = sample()
        old = parse_manifest(archive_files([first])[MANIFEST])
        other = sample(url=SOURCE[:-1] + "4", title="Other")
        merged = parse_manifest(archive_files([other], old)[MANIFEST])
        self.assertEqual(set(merged), {first.key, other.key})

    def test_renamed_title_retains_previous_path(self):
        old = parse_manifest(archive_files([sample()])[MANIFEST])
        new = sample(title="Renamed")
        files = archive_files([new], old)
        self.assertIn(sample().path_for(1), files)
        self.assertNotIn(new.path_for(1), files)

    def test_invalid_manifest_never_overwrites_other_paths(self):
        previous = parse_manifest(archive_files([sample()])[MANIFEST])
        previous[sample().key]["files"][0]["path"] = "README.md"
        with self.assertRaises(ArchiveError):
            parse_manifest(json.dumps({"version": 2, "challenges": previous}))
        with self.assertRaises(ArchiveError):
            archive_files([sample()], previous)

    def test_duplicate_and_empty_questions_fail(self):
        with self.assertRaises(ArchiveError):
            archive_files([sample(), sample()])
        with self.assertRaises(ArchiveError):
            sample(questions=()).markdown(1)
        with self.assertRaises(ArchiveError):
            sample(questions=("",)).markdown(1)

    def test_redacts_known_sensitive_shapes(self):
        fake_flag = "SKY-" + "ABCD-" + "1234"
        self.assertNotIn(fake_flag, clean(fake_flag))
        self.assertNotIn("synthetic-value", clean("ctf" + "{synthetic-value}"))
        self.assertNotIn("synthetic-value", clean("ctf" + r"\{synthetic-value\}"))
        self.assertNotIn("token", clean("https://example.org/file?token=demo#part"))
        self.assertNotIn("user:pass", clean("https://user:pass@example.org/file"))
        instance = "https://" + "a" * 24 + "-8000.gateway.cityinthe.cloud/"
        self.assertNotIn("gateway", clean(instance))
        self.assertNotIn("a" * 32, clean("a" * 32))

    def test_module_links_are_scoped(self):
        route = f"/module/{WORLD_ID}/{MODULE_ID}"
        snapshot = {"links": [{"href": route, "title": "Network"}, {"href": route, "title": "Duplicate"},
                              {"href": route + "/" + CHALLENGE_ID, "title": "One"},
                              {"href": "/module/" + "9" * 24 + "/" + MODULE_ID, "title": "Other event"}]}
        self.assertEqual(len(links_for(snapshot, MODULE, f"/module/{WORLD_ID}/")), 1)
        self.assertEqual(len(links_for(snapshot, CHALLENGE, route + "/")), 1)

    def test_tokens_not_in_settings_representation(self):
        settings = config(DISCORD_BOT_TOKEN="sensitive-discord", GITHUB_TOKEN="sensitive-github")
        self.assertNotIn("sensitive", repr(settings))

    def test_schedule_and_owner_configuration(self):
        for overrides in ({"DISCORD_OWNER_IDS": ""}, {"SYNC_INTERVAL_MINUTES": "1"},
                          {"SYNC_INTERVAL_MINUTES": "60"}, {"HEADLESS": "maybe"},
                          {"SKYLINE_STATE_DIR": str(Path(__file__).resolve().parents[1])}):
            with self.subTest(overrides=overrides), self.assertRaises(ArchiveError):
                config(**overrides)
        self.assertEqual(config(SYNC_INTERVAL_MINUTES="60", SKYLINE_EVENT_URL=EVENT).interval, 60)

    def test_ten_minute_environment_schedule_boundaries(self):
        for interval in (0, 10, 60, 10080):
            with self.subTest(interval=interval):
                self.assertEqual(config(SYNC_INTERVAL_MINUTES=str(interval), SKYLINE_EVENT_URL=EVENT).interval, interval)
        for interval in (-1, 1, 9, 10081):
            with self.subTest(interval=interval), self.assertRaises(ArchiveError):
                config(SYNC_INTERVAL_MINUTES=str(interval), SKYLINE_EVENT_URL=EVENT)
        with self.assertRaises(ArchiveError):
            config(SYNC_INTERVAL_MINUTES="10")


class FakeGitHub(GitHub):
    def __init__(self, files=None, conflict=False, policy_failure=False):
        super().__init__(config(), None)
        self.files = dict(files or {})
        self.head = "head1"
        self.pending = {}
        self.requests = []
        self.conflict = conflict
        self.policy_failure = policy_failure

    async def request(self, method, path, payload=None):
        self.requests.append((method, path, payload))
        if path.startswith("/git/ref/"):
            return {"object": {"sha": self.head}}
        if path.startswith("/git/commits/"):
            return {"tree": {"sha": "tree1"}}
        if path.startswith("/git/trees/"):
            return {"tree": [{"path": p, "type": "blob", "sha": git_blob_sha(c)} for p, c in self.files.items()]}
        if path.startswith("/contents/"):
            raw = self.files.get(MANIFEST)
            if raw is None:
                raise ApiError(404)
            return {"encoding": "base64", "content": base64.b64encode(raw.encode()).decode()}
        if path == "/git/trees":
            self.pending = {e["path"]: e["content"] for e in payload["tree"]}
            return {"sha": "new-tree"}
        if path == "/git/commits":
            return {"sha": "new-commit"}
        if method == "PATCH":
            if self.policy_failure:
                raise ApiError(422)
            if self.conflict:
                self.conflict = False
                self.head = "head2"
                self.files["concurrent.md"] = "Concurrent user's change.\n"
                raise ApiError(422)
            self.files.update(self.pending)
            return {"object": {"sha": "new-commit"}}
        raise AssertionError((method, path))


class PublishTests(unittest.IsolatedAsyncioTestCase):
    async def test_atomic_batch_preserves_unrelated_files_and_uses_no_force(self):
        git = FakeGitHub({"README.md": "Existing readme\n"})
        result = await git.publish([sample()])
        self.assertEqual(result.changed, 3)
        self.assertEqual(git.files["README.md"], "Existing readme\n")
        patches = [p for m, _, p in git.requests if m == "PATCH"]
        self.assertEqual(patches, [{"sha": "new-commit", "force": False}])

    async def test_repeat_sync_creates_no_commit(self):
        git = FakeGitHub(archive_files([sample()]))
        self.assertEqual((await git.publish([sample()])).changed, 0)
        self.assertFalse(any(m != "GET" for m, _, _ in git.requests))

    async def test_manual_edit_conflict_stops_before_any_write(self):
        files = archive_files([sample()])
        files[sample().path_for(1)] = "Manual edit\n"
        git = FakeGitHub(files)
        with self.assertRaises(ArchiveError):
            await git.publish([sample()])
        self.assertTrue(all(m == "GET" for m, _, _ in git.requests))

    async def test_concurrent_commit_is_merged_without_overwriting(self):
        git = FakeGitHub(conflict=True)
        await git.publish([sample()])
        self.assertIn("concurrent.md", git.files)
        parents = [p["parents"] for m, path, p in git.requests if path == "/git/commits"]
        self.assertEqual(parents, [["head1"], ["head2"]])

    async def test_policy_rejection_does_not_loop_or_force(self):
        git = FakeGitHub(policy_failure=True)
        with self.assertRaises(ApiError):
            await git.publish([sample()])
        self.assertEqual(sum(m == "PATCH" for m, _, _ in git.requests), 1)


class FakeProbe:
    def __init__(self, readiness):
        self.readiness = iter(readiness)

    async def check(self, watch):
        return next(self.readiness), "Synthetic check", "https://example.org/survey"


class SurveyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "watches.json"
        self.sent = []

    async def sender(self, watch, url):
        self.sent.append((watch["owner_id"], url))
        return 12345

    def manager(self, states, sender=None):
        manager = SurveyManager(self.path, FakeProbe(states), sender or self.sender)
        key = manager.add(SOURCE, "https://example.org/survey", "", 456, 789, 123)
        return manager, key

    async def test_two_successes_then_one_ping_across_restart(self):
        manager, key = self.manager([False, True, True])
        await manager.tick()
        await manager.tick()
        self.assertEqual(self.sent, [])
        await manager.tick()
        self.assertEqual(len(self.sent), 1)
        restored = SurveyManager(self.path, FakeProbe([]), self.sender)
        await restored.tick()
        self.assertEqual(restored.watches[key]["delivery"], "sent")
        self.assertEqual(len(self.sent), 1)

    async def test_failed_check_resets_readiness_streak(self):
        manager, _ = self.manager([True, False, True, True])
        for _ in range(3):
            await manager.tick()
        self.assertFalse(self.sent)
        await manager.tick()
        self.assertEqual(len(self.sent), 1)

    async def test_ambiguous_delivery_never_retries_automatically(self):
        async def fail(watch, url):
            raise ConnectionError("Synthetic network failure")
        manager, key = self.manager([True, True], fail)
        await manager.tick()
        await manager.tick()
        restored = SurveyManager(self.path, FakeProbe([]), self.sender)
        await restored.tick()
        self.assertEqual(restored.watches[key]["delivery"], "uncertain")
        self.assertFalse(self.sent)

    async def test_restart_during_delivery_does_not_resend(self):
        manager, key = self.manager([])
        manager.watches[key]["delivery"] = "sending"
        manager.save()
        restored = SurveyManager(self.path, FakeProbe([]), self.sender)
        await restored.tick()
        self.assertEqual(restored.watches[key]["delivery"], "uncertain")

    async def test_duplicate_watch_rejected(self):
        manager, _ = self.manager([])
        with self.assertRaises(ArchiveError):
            manager.add(SOURCE, "https://example.org/survey", "", 456, 789, 123)

    def test_loading_page_and_closed_form_are_not_ready(self):
        self.assertFalse(is_ready({"text": "Survey is open", "fields": 0, "actions": 0}))
        self.assertFalse(is_ready({"text": "Not accepting responses", "fields": 2, "actions": 1}))
        self.assertFalse(is_ready({"text": "Sign in", "fields": 2, "actions": 1, "password": True}))
        self.assertFalse(is_ready({"text": "Sign in\nUse your account", "fields": 1, "actions": 1}))
        self.assertTrue(is_ready({"text": "Event feedback", "fields": 2, "actions": 1}))
        self.assertFalse(is_ready({"text": "Event feedback", "fields": 2, "actions": 1}, "Different survey"))

    def test_survey_url_rejects_private_and_non_https_destinations(self):
        for url in ("http://example.org", "https://localhost", "https://127.0.0.1", "https://192.168.1.1",
                    "https://user:pass@example.org", "https://[::1]", "https://example.org:8080", "javascript:alert(1)"):
            with self.subTest(url=url), self.assertRaises(ArchiveError):
                form_url(url)
        self.assertEqual(form_url("https://example.org/form?event=demo"), "https://example.org/form?event=demo")


if __name__ == "__main__":
    unittest.main()
