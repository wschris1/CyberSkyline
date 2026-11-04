"""Deployment integrity and credential preservation without network access."""

import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pebblehost_entry", ROOT / "deploy/pebblehost/bot.py")
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class PebbleHostTests(unittest.TestCase):
    def test_release_hashes_match_application(self):
        self.assertGreater(len(ENTRY.SOURCE_FILES), 5)
        for relative, expected in ENTRY.SOURCE_FILES.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected, relative)
        self.assertEqual((ROOT / "deploy/pebblehost/requirements.txt").read_bytes(),
                         (ROOT / "bots/skyline_archive/requirements.txt").read_bytes())

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


if __name__ == "__main__":
    unittest.main()
