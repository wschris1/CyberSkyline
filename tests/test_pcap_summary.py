"""Synthetic classic-PCAP fixtures check format parsing and bounded output."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools import pcap_summary


def pcap(endian="<", nano=False, packets=(), snaplen=65535, linktype=1, version=(2, 4)):
    magic = (b"\x4d\x3c\xb2\xa1" if nano else b"\xd4\xc3\xb2\xa1") if endian == "<" else (
        b"\xa1\xb2\x3c\x4d" if nano else b"\xa1\xb2\xc3\xd4"
    )
    data = bytearray(magic + struct.pack(endian + "HHIIII", *version, 0, 0, snaplen, linktype))
    for seconds, fraction, payload, original in packets:
        data.extend(struct.pack(endian + "IIII", seconds, fraction, len(payload), original))
        data.extend(payload)
    return bytes(data)


class PCAPSummaryTests(unittest.TestCase):
    def test_all_magic_variants_and_empty_capture(self):
        for endian in ("<", ">"):
            for nano in (False, True):
                with self.subTest(endian=endian, nano=nano):
                    result = pcap_summary.summarize(pcap(endian=endian, nano=nano))
                    self.assertEqual(result["packets_scanned"], 0)
                    self.assertIsNone(result["first_packet_utc"])
                    self.assertEqual(result["endianness"], "little" if endian == "<" else "big")
                    self.assertEqual(result["timestamp_resolution"], "nanoseconds" if nano else "microseconds")
                    self.assertFalse(result["packet_limit_reached"])

    def test_little_endian_microseconds_counts_and_private_payload(self):
        data = pcap(packets=[(1, 25, b"synthetic-secret", 20), (2, 50, b"x", 1)])
        result = pcap_summary.summarize(data)
        self.assertEqual(result["packets_scanned"], 2)
        self.assertEqual(result["captured_bytes"], 17)
        self.assertEqual(result["original_bytes"], 21)
        self.assertEqual(result["capture_truncated_packets"], 1)
        self.assertEqual(result["first_packet_utc"], "1970-01-01T00:00:01.000025Z")
        self.assertEqual(result["last_packet_utc"], "1970-01-01T00:00:02.000050Z")
        self.assertFalse(result["packet_limit_reached"])
        self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_big_endian_nanoseconds_and_out_of_order(self):
        data = pcap(endian=">", nano=True, packets=[(3, 9, b"ab", 2), (2, 1, b"z", 1)])
        result = pcap_summary.summarize(data)
        self.assertEqual(result["endianness"], "big")
        self.assertEqual(result["timestamp_resolution"], "nanoseconds")
        self.assertEqual(result["first_packet_utc"], "1970-01-01T00:00:03.000000009Z")
        self.assertEqual(result["earliest_packet_utc"], "1970-01-01T00:00:02.000000001Z")
        self.assertEqual(result["timestamp_order_reversals"], 1)
        self.assertTrue(result["warnings"])

    def test_packet_limit_marks_prefix_without_claiming_full_count(self):
        data = pcap(packets=[(1, 0, b"a", 1), (2, 0, b"b", 1)])
        result = pcap_summary.summarize(data, max_packets=1)
        self.assertEqual(result["packets_scanned"], 1)
        self.assertTrue(result["packet_limit_reached"])
        self.assertFalse(pcap_summary.summarize(data, max_packets=2)["packet_limit_reached"])
        with self.assertRaises(ValueError):
            pcap_summary.summarize(data, max_packets=0)

    def test_rejects_wrong_format_and_truncated_records(self):
        valid = pcap(packets=[(1, 0, b"abc", 3)])
        for data, message in (
            (b"\x0a\x0d\x0d\x0a" + b"\0" * 20, "PCAPNG"),
            (b"not-a-pcap" + b"\0" * 20, "magic"),
            (valid[:23], "file header"),
            (valid[:30], "record header"),
            (valid[:-1], "packet data"),
            (pcap(snaplen=0), "snapshot length"),
            (pcap(version=(3, 0)), "major version"),
            (pcap(packets=[(1, 1_000_000, b"x", 1)]), "timestamp fraction"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                pcap_summary.summarize(data)

    def test_inconsistent_lengths_and_reserved_bits_are_warnings(self):
        data = pcap(snaplen=2, linktype=0xF8000001, packets=[(1, 0, b"abc", 2)])
        result = pcap_summary.summarize(data)
        self.assertEqual(result["length_inconsistent_packets"], 1)
        self.assertEqual(result["linktype"], 1)
        self.assertEqual(result["linktype_word_hex"], "0xf8000001")
        self.assertGreaterEqual(len(result["warnings"]), 2)

    def test_cli_never_prints_payload_and_rejects_oversize(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as root:
            path = Path(root) / "capture.pcap"
            path.write_bytes(pcap(packets=[(1, 0, b"synthetic-private-data", 22)]))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = pcap_summary.main([str(path)])
            self.assertEqual(code, 0)
            self.assertNotIn("synthetic-private-data", out.getvalue())
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(pcap_summary.main([str(path), "--max-bytes", "25"]), 1)


if __name__ == "__main__":
    unittest.main()
