from __future__ import annotations

import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from tools.artifact_inventory import identify, inventory
from tools.candidate_filter import Constraints, fits
from tools.decode_value import decode
from tools.new_challenge import create_challenge, valid_slug
from tools.safe_extract import (
    UnsafeArchive,
    extract_zip,
    prepare_destination,
    tar_entries,
    validate,
    zip_entries,
)
from tools.timestamp_convert import convert
from tools.url_inventory import inventory as url_inventory


class ArtifactInventoryTests(unittest.TestCase):
    def test_hash_and_signature(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            data = b"SQLite format 3\x00rest"
            path.write_bytes(data)
            records = inventory([path], Path(directory))
            self.assertEqual(records[0]["path"], "sample.bin")
            self.assertEqual(records[0]["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(identify(path), "SQLite database")


class SafeExtractTests(unittest.TestCase):
    def test_regular_zip_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "input.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("folder/evidence.txt", "evidence")
            with zipfile.ZipFile(archive_path) as archive:
                entries = zip_entries(archive)
                validate(entries, max_members=10, max_bytes=100)
            self.assertEqual(entries[0].kind, "file")

    def test_regular_zip_extracts_into_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "input.zip"
            destination = Path(directory) / "output"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("folder/evidence.txt", "evidence")
            with zipfile.ZipFile(archive_path) as archive:
                entries = zip_entries(archive)
                validate(entries, max_members=10, max_bytes=100)
                extract_zip(archive, entries, prepare_destination(destination))
            self.assertEqual((destination / "folder" / "evidence.txt").read_text(), "evidence")

    def test_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "input.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "no")
            with zipfile.ZipFile(archive_path) as archive:
                with self.assertRaises(UnsafeArchive):
                    validate(zip_entries(archive), max_members=10, max_bytes=100)

    def test_tar_links_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "input.tar"
            with tarfile.open(archive_path, "w") as archive:
                regular = tarfile.TarInfo("evidence.txt")
                regular.size = 2
                archive.addfile(regular, io.BytesIO(b"ok"))
                link = tarfile.TarInfo("linked.txt")
                link.type = tarfile.SYMTYPE
                link.linkname = "evidence.txt"
                archive.addfile(link)
            with tarfile.open(archive_path) as archive:
                with self.assertRaises(UnsafeArchive):
                    validate(tar_entries(archive), max_members=10, max_bytes=100)


class ConversionTests(unittest.TestCase):
    def test_timestamp_epochs(self) -> None:
        self.assertEqual(convert("0", "unix-s"), "1970-01-01T00:00:00.000000Z")
        self.assertEqual(
            convert("11644473600000000", "webkit-us"),
            "1970-01-01T00:00:00.000000Z",
        )

    def test_explicit_decoding(self) -> None:
        self.assertEqual(decode("4142", "hex"), (b"AB", True))
        self.assertEqual(decode("QUI", "base64"), (b"AB", True))
        self.assertEqual(decode("a+b%20c", "url"), (b"a+b c", None))
        self.assertEqual(decode("a+b%20c", "form"), (b"a b c", None))


class TextTriageTests(unittest.TestCase):
    def test_url_values_are_redacted(self) -> None:
        records = url_inventory(["See https://Example.test/a?token=secret&x=1#private"])
        self.assertEqual(records[0]["host"], "example.test")
        self.assertEqual(records[0]["query_keys"], ["token", "x"])
        self.assertNotIn("secret", str(records[0]["url"]))
        self.assertNotIn("private", str(records[0]["url"]))

    def test_candidate_constraints_apply_to_final_value(self) -> None:
        constraints = Constraints(min_length=10, uppercase=1, special=1, ascii_only=True)
        self.assertTrue(fits("Abcdefghi!", constraints))
        self.assertFalse(fits("ABcdefghi!", constraints))


class ChallengeScaffoldTests(unittest.TestCase):
    def test_slug_validation(self) -> None:
        self.assertTrue(valid_slug("sample-challenge-2"))
        self.assertFalse(valid_slug("Sample Challenge"))
        self.assertFalse(valid_slug("../escape"))

    def test_creation_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "challenges").mkdir()
            destination = create_challenge(root, "sample", "Sample")
            self.assertTrue((destination / "question.md").is_file())
            self.assertTrue((destination / "how-to-solve.md").is_file())
            with self.assertRaises(FileExistsError):
                create_challenge(root, "sample", "Sample")
            with self.assertRaises(ValueError):
                create_challenge(root, "another", "two\nlines")


if __name__ == "__main__":
    unittest.main()
