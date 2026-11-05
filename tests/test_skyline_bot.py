"""Exercise scan cancellation without connecting to Discord or real accounts."""

import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bots.skyline_archive.core import ArchiveError, Challenge
from bots.skyline_archive.scanner import ScanResult

try:
    from bots.skyline_archive.bot import SkylineBot, SkylineCommands
except ModuleNotFoundError as exc:
    if exc.name not in {"discord", "aiohttp"}:
        raise
    SkylineBot = None


@unittest.skipIf(SkylineBot is None, "Install optional bot requirements to test Discord controls")
class ScanControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(
            guild_id=123, owners={456}, repository="example/archive", interval=0,
            event_url="https://cyberskyline.com/world/" + "1" * 24,
            state_dir=Path(self.directory.name), headless=True,
            auth_file=Path(self.directory.name) / "session.json")
        self.client = SkylineBot(self.settings)
        self.entered = asyncio.Event()
        self.cleanup = asyncio.Event()
        self.release_cleanup = asyncio.Event()
        self.release_cleanup.set()

        async def collect(*args, **kwargs):
            self.entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cleanup.set()
                await self.release_cleanup.wait()

        self.collect = AsyncMock(side_effect=collect)
        self.scanner_patch = patch("bots.skyline_archive.bot.Scanner")
        self.scanner = self.scanner_patch.start()
        self.scanner.return_value.collect = self.collect
        self.github_patch = patch("bots.skyline_archive.bot.GitHub")
        self.github = self.github_patch.start()
        self.publish = AsyncMock(return_value=SimpleNamespace(changed=0, commit_url=None))
        self.github.return_value.publish = self.publish

    async def asyncTearDown(self):
        self.release_cleanup.set()
        await self.client.close()
        self.github_patch.stop()
        self.scanner_patch.stop()
        self.directory.cleanup()

    async def finished(self):
        await asyncio.gather(self.client.scan_task, return_exceptions=True)
        await asyncio.sleep(0)  # Deliver the task's completion callback.

    async def test_stop_when_idle_preserves_previous_result(self):
        self.client.archive_status = "Previous result"
        self.assertIn("No scan is running", self.client.stop_sync())
        self.assertEqual(self.client.archive_status, "Previous result")

    async def test_stop_before_task_starts_and_restart(self):
        self.client.start_sync(all_events=True)
        self.assertIn("Stop requested", self.client.stop_sync())
        await self.finished()
        self.collect.assert_not_awaited()
        self.publish.assert_not_awaited()
        self.assertIn("Scan stopped. Saved questions and completed posts are preserved", self.client.archive_status)
        self.client.start_sync(all_events=True, preview=True)
        await asyncio.wait_for(self.entered.wait(), 3)
        self.client.stop_sync()
        await self.finished()
        self.assertTrue(self.cleanup.is_set())

    async def test_stop_preview_and_upload_scans_without_publishing(self):
        for preview in (True, False):
            with self.subTest(preview=preview):
                self.entered.clear()
                self.cleanup.clear()
                self.client.start_sync(all_events=True, preview=preview)
                await asyncio.wait_for(self.entered.wait(), 3)
                self.client.stop_sync()
                await self.finished()
                self.assertTrue(self.cleanup.is_set())
                self.assertTrue(self.client.scan_task.cancelled())
                self.assertEqual(self.client.scan_phase, "idle")
                self.assertIn("Scan stopped", self.client.archive_status)
        self.publish.assert_not_awaited()

    async def test_repeated_stop_does_not_interrupt_browser_cleanup(self):
        self.release_cleanup.clear()
        self.client.start_sync(all_events=True)
        await asyncio.wait_for(self.entered.wait(), 3)
        self.client.stop_sync()
        await self.cleanup.wait()
        self.assertIn("already stopping", self.client.stop_sync())
        with self.assertRaisesRegex(ArchiveError, "already running"):
            self.client.start_sync(all_events=True)
        self.assertFalse(self.client.scan_task.done())
        self.release_cleanup.set()
        await self.finished()
        self.assertIn("Scan stopped", self.client.archive_status)
        self.publish.assert_not_awaited()

    async def test_stop_does_not_cancel_publication_already_in_progress(self):
        publishing = asyncio.Event()
        finish_publication = asyncio.Event()

        async def publish(*args):
            publishing.set()
            await finish_publication.wait()
            return SimpleNamespace(changed=3, commit_url="https://github.com/example/archive/commit/example")

        self.collect.side_effect = None
        self.collect.return_value = ScanResult(challenges=[Challenge("https://cyberskyline.com/module/"+"1"*24+"/"+"2"*24+"/"+"3"*24, "NCL Fall 2026 Gymnasium", "Forensics", "Example (Easy)", "Instructions", ("Example question?",))])
        self.publish.side_effect = publish
        self.client.start_sync(all_events=True)
        await asyncio.wait_for(publishing.wait(), 3)
        self.assertIn("already started and cannot be cancelled", self.client.stop_sync())
        self.assertFalse(self.client.scan_task.done())
        finish_publication.set()
        await self.finished()
        self.assertIn("Complete:", self.client.archive_status)
        self.assertIn("3 files changed", self.client.archive_status)
        self.assertEqual(self.client.scan_phase, "idle")

    async def test_completed_preview_cannot_be_stopped_or_published(self):
        self.collect.side_effect = None
        self.collect.return_value = ScanResult(challenges=[Challenge("https://cyberskyline.com/module/"+"1"*24+"/"+"2"*24+"/"+"3"*24, "NCL Fall 2026 Gymnasium", "Forensics", "Example (Easy)", "Instructions", ("Example question?",))])
        self.client.start_sync(all_events=True, preview=True)
        await self.finished()
        previous = self.client.archive_status
        self.assertIn("Preview complete", previous)
        self.assertIn("No scan is running", self.client.stop_sync())
        self.assertEqual(self.client.archive_status, previous)
        self.publish.assert_not_awaited()

    async def test_cancelling_real_scanner_closes_browser_and_leaves_other_tasks_running(self):
        self.scanner_patch.stop()
        self.settings.auth_file.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
        visit_started = asyncio.Event()

        async def visit(*args):
            visit_started.set()
            await asyncio.Event().wait()

        browser = SimpleNamespace(new_context=AsyncMock(), close=AsyncMock())
        browser.new_context.return_value.new_page = AsyncMock()
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        manager = AsyncMock()
        manager.__aenter__.return_value = runtime
        other_task = asyncio.create_task(asyncio.Event().wait())
        self.client.background.append(other_task)
        with (patch("playwright.async_api.async_playwright", return_value=manager),
              patch("bots.skyline_archive.scanner.Scanner.visit", side_effect=visit)):
            self.client.start_sync(all_events=True)
            await asyncio.wait_for(visit_started.wait(), 3)
            self.client.stop_sync()
            await self.finished()
        browser.close.assert_awaited_once()
        self.assertFalse(other_task.done())
        self.publish.assert_not_awaited()

    async def test_stop_command_is_owner_only_and_replies_privately(self):
        commands = SkylineCommands(self.client)
        interaction = SimpleNamespace(guild_id=123, user=SimpleNamespace(id=789),
                                      response=SimpleNamespace(send_message=AsyncMock()))
        self.assertFalse(await commands.interaction_check(interaction))
        interaction.user.id = 456
        self.assertTrue(await commands.interaction_check(interaction))
        await commands.get_command("stop").callback(commands, interaction)
        self.assertIn("No scan is running", interaction.response.send_message.call_args.args[0])
        self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])

    async def test_status_identifies_preview_mode(self):
        commands = SkylineCommands(self.client)
        interaction = SimpleNamespace(response=SimpleNamespace(send_message=AsyncMock()))
        self.client.start_sync(all_events=True, preview=True)
        await asyncio.wait_for(self.entered.wait(), 3)
        await commands.get_command("status").callback(commands, interaction)
        self.assertIn("Preview (no uploads)", interaction.response.send_message.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
