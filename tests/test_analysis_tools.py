"""Synthetic fixtures exercise byte accuracy, bounded output, and read-only behavior."""

import base64
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from tools import binary_diff, entropy_scan, hex_view, http_response_inspect
from tools import jsonl_summary, signature_scan, sqlite_inspect, ssh_public_key, strings_extract, xor_bytes
from tools._common import read_bytes


ROOT = Path(__file__).resolve().parents[1]


class TemporaryFiles:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def file(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path


class FileTests(TemporaryFiles, unittest.TestCase):
    def test_bounded_read_rejects_oversize_and_symlink(self):
        source = self.file("sample", b"12345")
        self.assertEqual(read_bytes(source, 5), b"12345")
        with self.assertRaises(ValueError):
            read_bytes(source, 4)
        link = self.root / "link"
        link.symlink_to(source)
        with self.assertRaises(ValueError):
            read_bytes(link)

    def test_hex_range_retains_absolute_offsets_and_end_of_file(self):
        source = self.file("sample", b"\x00abc\xffz")
        result = hex_view.view(source, 2, 99, 2)
        self.assertEqual(result["shown_bytes"], 4)
        self.assertEqual(result["rows"], [
            {"offset": 2, "hex": "62 63", "ascii": "bc"},
            {"offset": 4, "hex": "ff 7a", "ascii": ".z"},
        ])
        self.assertEqual(hex_view.view(source, 6, 1)["rows"], [])
        with self.assertRaises(ValueError):
            hex_view.view(source, 7, 1)

    def test_xor_cli_preserves_existing_destination(self):
        source = self.file("source", b"\x00\xff\n")
        destination = self.file("output", b"preserved")
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            result = xor_bytes.main([str(source), "--key-hex", "20", "--output", str(destination)])
        self.assertEqual(result, 1)
        self.assertEqual(destination.read_bytes(), b"preserved")
        self.assertEqual(source.read_bytes(), b"\x00\xff\n")


class BinaryTests(unittest.TestCase):
    def test_strings_exact_offsets_with_unaligned_utf16(self):
        data = b"\xffHi!\x00" + "Wide".encode("utf-16le") + b"\xff" + "BEAM".encode("utf-16be")
        ascii_rows = strings_extract.extract(data, minimum=3, encoding="ascii")["strings"]
        self.assertEqual(ascii_rows, [{"offset": 1, "encoding": "ascii", "text": "Hi!"}])
        little = strings_extract.extract(data, encoding="utf-16le")["strings"]
        self.assertIn({"offset": 3, "encoding": "utf-16le", "text": "!Wide"}, little)
        big = strings_extract.extract(data, encoding="utf-16be")["strings"]
        self.assertIn({"offset": 14, "encoding": "utf-16be", "text": "BEAM"}, big)

    def test_strings_limits_are_reported(self):
        result = strings_extract.extract(b"hello\x00world\x00again", encoding="ascii", limit=2)
        self.assertEqual(len(result["strings"]), 2)
        self.assertTrue(result["truncated"])
        with self.assertRaises(ValueError):
            strings_extract.extract(b"", minimum=5000)

    def test_diff_detects_tail_and_separate_ranges(self):
        result = binary_diff.compare(b"abcde", b"axcDeZ")
        self.assertEqual(result["differing_offsets"], 3)
        self.assertEqual([(row["start"], row["end_exclusive"]) for row in result["ranges"]], [(1, 2), (3, 4), (5, 6)])
        self.assertEqual(result["ranges"][-1]["left_preview_hex"], "")
        self.assertFalse(result["equal"])

    def test_diff_truncates_display_without_losing_totals(self):
        result = binary_diff.compare(b"a0b0c", b"a1b1c", limit=1)
        self.assertEqual(result["range_count"], 2)
        self.assertEqual(result["differing_offsets"], 2)
        self.assertTrue(result["truncated"])
        self.assertTrue(binary_diff.compare(b"", b"")["equal"])

    def test_entropy_reference_distributions(self):
        self.assertEqual(entropy_scan.entropy(b"a" * 4096), 0)
        self.assertEqual(entropy_scan.entropy(bytes(range(256))), 8)
        self.assertEqual(entropy_scan.entropy(b"ab" * 20), 1)

    def test_entropy_partial_window_and_limit(self):
        result = entropy_scan.scan(b"aabbccx", window=3, step=3)
        self.assertEqual([row["bytes"] for row in result["windows"]], [3, 3, 1])
        self.assertEqual(result["windows"][-1]["offset"], 6)
        self.assertTrue(entropy_scan.scan(b"abcdef", window=2, limit=1)["truncated"])

    def test_signature_offsets_and_false_positive_label(self):
        data = b"junk" + b"\x89PNG\r\n\x1a\n" + b"PK\x03\x04"
        result = signature_scan.scan(data)
        self.assertEqual([row["offset"] for row in result["matches"]], [4, 12])
        self.assertFalse(result["validated_formats"])
        self.assertTrue(signature_scan.scan(data, limit=1)["truncated"])

    def test_xor_known_vector_round_trip_and_key_phase(self):
        self.assertEqual(xor_bytes.transform(b"ABC", b"\x20"), b"abc")
        data = bytes(range(256))
        encrypted = xor_bytes.transform(data, b"\x00\x55\xff", offset=2)
        self.assertEqual(encrypted[:3], bytes([255, 1, 87]))
        self.assertEqual(xor_bytes.transform(encrypted, b"\x00\x55\xff", offset=2), data)
        with self.assertRaises(ValueError):
            xor_bytes.transform(data, b"")


class HTTPTests(unittest.TestCase):
    def test_duplicate_headers_and_private_values(self):
        data = b"HTTP/1.1 200 OK\r\nSet-Cookie: first=secret\r\nSet-Cookie: second=secret\r\nContent-Length: 3\r\n\r\nabc"
        result = http_response_inspect.inspect(data)
        self.assertEqual(len(result["headers"]), 3)
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(result["trailing_sha256"], hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(result["warnings"], [])
        self.assertIn("secret", json.dumps(http_response_inspect.inspect(data, show_values=True)))

    def test_informational_response_before_final_response(self):
        result = http_response_inspect.inspect(b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 204 No Content\r\n\r\n")
        self.assertEqual(result["informational_statuses"], [100])
        self.assertEqual(result["status"], 204)

    def test_content_length_conflicts_and_transfer_encoding(self):
        result = http_response_inspect.inspect(b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n")
        self.assertIsNone(result["declared_content_length"])
        self.assertIn("conflicting Content-Length values", result["warnings"])
        self.assertIn("both Transfer-Encoding and Content-Length are present", result["warnings"])

    def test_identical_lengths_and_head_semantics(self):
        data = b"HTTP/1.1 200 OK\r\nContent-Length: 12, 12\r\n\r\n"
        self.assertEqual(http_response_inspect.inspect(data, request_method="HEAD")["warnings"], [])
        self.assertTrue(http_response_inspect.inspect(data)["warnings"])
        self.assertEqual(http_response_inspect.inspect(data, headers_only=True)["warnings"], [])

    def test_rejects_folded_or_malformed_headers(self):
        for data in (b"HTTP/1.1 200 OK\r\n folded\r\n\r\n", b"HTTP/1.1 200 OK\r\nBad Name: x\r\n\r\n", b"HTTP/1.1 200 OK\r\nX: \x00\r\n\r\n", b"not a response"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                http_response_inspect.inspect(data)


class JSONLTests(unittest.TestCase):
    def test_schema_does_not_print_record_values(self):
        result = jsonl_summary.summarize(io.BytesIO(b'{"token":"synthetic-private"}\n{"token":null}\n'))
        self.assertNotIn("synthetic-private", json.dumps(result))
        self.assertEqual(result["keys"]["token"], {"string": 1, "null": 1})

    def test_literal_dotted_fields_distinguish_null_missing_and_types(self):
        rows = [{"id.orig_h": "example"}, {"id.orig_h": None}, {}, {"id.orig_h": 1}, {"id.orig_h": True}, {"id.orig_h": []}]
        stream = io.BytesIO("\n".join(json.dumps(row) for row in rows).encode())
        result = jsonl_summary.summarize(stream, "id.orig_h")["field_counts"]
        self.assertEqual(result["missing"], 1)
        self.assertEqual(result["non_scalar"], 1)
        self.assertEqual(len(result["values"]), 4)

    def test_invalid_lines_are_counted_without_echoing_content(self):
        data = b'{}\n\n{"x":1,"x":2}\nnot-json\n\xff\n{"x":NaN}\n{"x":1e999}\n'
        result = jsonl_summary.summarize(io.BytesIO(data))
        self.assertEqual(result["valid_records"], 1)
        self.assertEqual(result["blank_lines"], 1)
        self.assertEqual(result["invalid_line_numbers_first_20"], [3, 4, 5, 6, 7])
        self.assertEqual(result["invalid_records"], 5)

    def test_line_and_group_limits(self):
        result = jsonl_summary.summarize(io.BytesIO(b'{}\n{}\n'), max_lines=1)
        self.assertTrue(result["truncated"])
        with self.assertRaises(ValueError):
            jsonl_summary.summarize(io.BytesIO(b'{"long":123}\n'), max_line_bytes=5)
        with self.assertRaises(ValueError):
            jsonl_summary.summarize(io.BytesIO(b'{"x":1}\n{"x":2}\n'), field="x", max_groups=1)


class SQLiteTests(TemporaryFiles, unittest.TestCase):
    def database(self):
        path = self.root / "sample database.db"
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE "odd name" (id INTEGER, payload BLOB)')
            connection.executemany('INSERT INTO "odd name" VALUES (?, ?)', [(1, b"abc"), (2, b"xyz")])
        return path

    def test_read_only_schema_rows_and_blob_summary(self):
        path = self.database()
        before = path.read_bytes()
        result = sqlite_inspect.inspect(path)
        self.assertIn(["table", "odd name", "odd name"], result["rows"])
        result = sqlite_inspect.inspect(path, 'SELECT * FROM "odd name" ORDER BY id', limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["rows"][0][1]["sha256"], hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(path.read_bytes(), before)

    def test_missing_database_is_not_created(self):
        path = self.root / "missing.db"
        with self.assertRaises(ValueError):
            sqlite_inspect.inspect(path)
        self.assertFalse(path.exists())

    def test_writes_attach_and_pragma_are_denied(self):
        path = self.database()
        for statement in ('DELETE FROM "odd name"', "ATTACH DATABASE ':memory:' AS other", "PRAGMA user_version=5", "SELECT load_extension('absent')"):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.Error):
                sqlite_inspect.inspect(path, statement)
        self.assertEqual(sqlite_inspect.inspect(path, 'SELECT COUNT(*) FROM "odd name"')["rows"], [[2]])

    def test_recursive_query_has_execution_budget(self):
        path = self.database()
        query = "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT SUM(x) FROM n"
        with self.assertRaisesRegex(sqlite3.OperationalError, "interrupted"):
            sqlite_inspect.inspect(path, query, budget=1000)


def ssh_string(value):
    return len(value).to_bytes(4, "big") + value


class SSHKeyTests(unittest.TestCase):
    def ed25519(self, key=bytes(range(32)), extra=b""):
        blob = ssh_string(b"ssh-ed25519") + ssh_string(key) + extra
        return "ssh-ed25519 " + base64.b64encode(blob).decode() + " private-comment", blob

    def test_fingerprint_and_comment_omission(self):
        text, blob = self.ed25519()
        result = ssh_public_key.inspect(text)
        expected = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        self.assertEqual(result["fingerprint"], expected)
        self.assertEqual(result["key_bits"], 256)
        self.assertNotIn("private-comment", json.dumps(result))

    def test_truncated_wrong_type_wrong_size_and_trailing_data(self):
        text, blob = self.ed25519()
        samples = [text.replace("ssh-ed25519 ", "ssh-rsa ", 1), self.ed25519(b"short")[0], self.ed25519(extra=b"x")[0],
                   "ssh-ed25519 " + base64.b64encode(blob[:-1]).decode()]
        for sample in samples:
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                ssh_public_key.inspect(sample)

    def test_rsa_canonical_mpints(self):
        blob = ssh_string(b"ssh-rsa") + ssh_string(b"\x03") + ssh_string(b"\x00\x81")
        result = ssh_public_key.inspect("ssh-rsa " + base64.b64encode(blob).decode())
        self.assertEqual(result["key_bits"], 8)
        for value in (b"", b"\x80", b"\x00\x01", b"\x00"):
            with self.assertRaises(ValueError):
                ssh_public_key.positive_mpint(value)

    @unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH is unavailable for independent comparison")
    def test_fingerprint_agrees_with_openssh(self):
        text, _ = self.ed25519()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "synthetic.pub"
            path.write_text(text + "\n")
            result = subprocess.run(["ssh-keygen", "-lf", str(path), "-E", "sha256"], capture_output=True, text=True, check=True)
        self.assertIn(ssh_public_key.inspect(text)["fingerprint"], result.stdout)


class CommandLineTests(unittest.TestCase):
    def test_every_public_tool_has_working_help(self):
        for path in sorted((ROOT / "tools").glob("*.py")):
            if path.name.startswith("_"):
                continue
            with self.subTest(tool=path.name):
                result = subprocess.run([sys.executable, str(path), "--help"], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
