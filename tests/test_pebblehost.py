"""Deployment integrity and credential preservation without network access."""

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import shutil
import json
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pebblehost_entry", ROOT / "deploy/pebblehost/bot.py")
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class PebbleHostTests(unittest.TestCase):
    def test_discord_startup_does_not_require_skyline_login(self):
        for has_session in (False, True):
            with self.subTest(has_session=has_session), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = root / "private/skyline-archive"
                state.mkdir(parents=True)
                session = state / "browser-state.json"
                if has_session:
                    session.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
                runner = Mock()
                modules = {
                    "dotenv": SimpleNamespace(load_dotenv=Mock()),
                    "discord": SimpleNamespace(), "aiohttp": SimpleNamespace(),
                    "playwright": SimpleNamespace(),
                    "bots.skyline_archive.settings": SimpleNamespace(
                        load_settings=lambda **kwargs: SimpleNamespace(auth_file=session)),
                    "bots.skyline_archive.__main__": SimpleNamespace(main=runner),
                }
                environment = {name: "test-value" for name in
                               ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID", "DISCORD_OWNER_IDS", "GITHUB_TOKEN")}
                with (patch.object(ENTRY, "__file__", str(root / "bot.py")),
                      patch.object(ENTRY, "install_source", return_value=root / "skyline-app"),
                      patch.object(ENTRY, "prepare_private", return_value=(root / "private/skyline.env", state)),
                      patch.object(ENTRY, "prepare_browser_libraries"),
                      patch.object(ENTRY, "browser_check", new_callable=AsyncMock),
                      patch.object(ENTRY.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
                      patch.dict(ENTRY.os.environ, environment),
                      patch.dict(ENTRY.sys.modules, modules),
                      patch.object(ENTRY.sys, "path", ENTRY.sys.path.copy()),
                      patch.object(ENTRY.sys, "argv", ["bot.py"]),
                      patch.object(ENTRY.os, "umask"),
                      patch("sys.stdout", new_callable=io.StringIO)):
                    self.assertEqual(ENTRY.main(), 0)
                runner.assert_called_once_with()
                status = (root / "setup-status.txt").read_text()
                self.assertIn("Starting the Discord connection", status)
                self.assertEqual("CYBER SKYLINE LOGIN NEEDED" in status, not has_session)

    def test_release_hashes_match_application(self):
        self.assertGreater(len(ENTRY.SOURCE_FILES), 5)
        for relative, expected in ENTRY.SOURCE_FILES.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected, relative)
        self.assertEqual((ROOT / "deploy/pebblehost/requirements.txt").read_bytes(),
                         (ROOT / "bots/skyline_archive/requirements.txt").read_bytes())

    def test_pinned_package_contains_verification_runtime_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ENTRY.SOURCE_FILES:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            payload = dict(question='What is the decoded hex value?', instructions='Input: `412042`',
                           files=[], root=str(root), answer='A B')
            result = subprocess.run([sys.executable, '-I', str(root / 'bots/skyline_archive/verify_worker.py')],
                                    input=json.dumps(payload),capture_output=True,text=True,timeout=10,cwd=directory)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['outcome'],'Verified correct')

    def test_rejects_changed_existing_source_and_download(self):
        original = b"verified source\n"
        manifest = {"bots/example.py": hashlib.sha256(original).hexdigest()}
        with tempfile.TemporaryDirectory() as directory, patch.dict(ENTRY.SOURCE_FILES, manifest, clear=True):
            root = Path(directory)
            destination = root / "skyline-app/bots/example.py"
            with patch.object(ENTRY.urllib.request, "urlopen", return_value=io.BytesIO(b"unexpected content")):
                with self.assertRaisesRegex(ENTRY.SetupError, "verification failed"):
                    ENTRY.install_source(root)
                self.assertFalse(destination.exists())
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"local edit")
            with patch.object(ENTRY.urllib.request, "urlopen") as download:
                with self.assertRaisesRegex(ENTRY.SetupError, "file changed"):
                    ENTRY.install_source(root)
                download.assert_not_called()
                self.assertEqual(destination.read_bytes(), b"local edit")

    def test_verified_download_is_reused(self):
        original = b"verified source\n"
        manifest = {"bots/example.py": hashlib.sha256(original).hexdigest()}
        with tempfile.TemporaryDirectory() as directory, patch.dict(ENTRY.SOURCE_FILES, manifest, clear=True):
            root = Path(directory)
            with patch.object(ENTRY.urllib.request, "urlopen", return_value=io.BytesIO(original)):
                app = ENTRY.install_source(root)
            with patch.object(ENTRY.urllib.request, "urlopen") as download:
                self.assertEqual(ENTRY.install_source(root), app)
                download.assert_not_called()

    def test_private_settings_survive_restarts_outside_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, state = ENTRY.prepare_private(root)
            config.write_text("DISCORD_GUILD_ID=123456\n", encoding="utf-8")
            session = state / "browser-state.json"
            session.write_text('{"cookies": []}', encoding="utf-8")
            self.assertEqual(ENTRY.prepare_private(root), (config, state))
            self.assertEqual(config.read_text(), "DISCORD_GUILD_ID=123456\n")
            self.assertTrue(session.is_file())
            self.assertFalse(state.is_relative_to(root / "skyline-app"))

    def test_missing_library_parser_ignores_resolved_paths(self):
        output = "\tlibnspr4.so => not found\n\tlibc.so.6 => /lib/libc.so.6 (0x123)\n"
        with patch.object(ENTRY.subprocess, "run", return_value=SimpleNamespace(stdout=output)):
            self.assertEqual(ENTRY.missing_libraries(Path("/test/browser")), {"libnspr4.so"})

    def test_unrecognized_library_stops_before_any_package_command(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            root = Path(directory)
            binary = root / "browser-cache/chromium_headless_shell-1/chrome-linux/chrome-headless-shell"
            binary.parent.mkdir(parents=True)
            binary.touch()
            with (patch.object(ENTRY, "missing_libraries", return_value={"libunknown.so.1"}),
                  patch.object(ENTRY.platform, "freedesktop_os_release", return_value={"ID": "ubuntu", "VERSION_ID": "26.04"}),
                  patch.object(ENTRY.platform, "machine", return_value="x86_64"),
                  patch.object(ENTRY.shutil, "which", return_value="/usr/bin/exists"),
                  patch.object(ENTRY.subprocess, "run") as command):
                with self.assertRaisesRegex(ENTRY.SetupError, "Unmapped browser libraries"):
                    ENTRY.prepare_browser_libraries(root)
                command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
