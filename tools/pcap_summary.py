#!/usr/bin/env python3
"""Summarize classic PCAP record metadata without reading packet payloads as protocols."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import struct
import sys

if __package__:
    from ._common import add_byte_limit, emit, positive, read_bytes
else:
    from _common import add_byte_limit, emit, positive, read_bytes


MAGIC = {
    b"\xa1\xb2\xc3\xd4": (">", "big", "microseconds", 1_000_000),
    b"\xd4\xc3\xb2\xa1": ("<", "little", "microseconds", 1_000_000),
    b"\xa1\xb2\x3c\x4d": (">", "big", "nanoseconds", 1_000_000_000),
    b"\x4d\x3c\xb2\xa1": ("<", "little", "nanoseconds", 1_000_000_000),
}
PCAPNG_MAGIC = b"\x0a\x0d\x0d\x0a"


def utc_timestamp(ticks: int, scale: int) -> str:
    seconds, fraction = divmod(ticks, scale)
    date = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return date.strftime("%Y-%m-%dT%H:%M:%S") + f".{fraction:0{6 if scale == 1_000_000 else 9}d}Z"


def summarize(data: bytes, max_packets: int = 100_000) -> dict:
    """Read file and record headers only; packet bytes are never returned."""
    if max_packets < 1:
        raise ValueError("packet limit must be positive")
    if data.startswith(PCAPNG_MAGIC):
        raise ValueError("PCAPNG is not supported; use Wireshark or TShark")
    if len(data) < 24:
        raise ValueError("truncated PCAP file header")
    magic = data[:4]
    if magic not in MAGIC:
        raise ValueError("unrecognized classic PCAP magic number")
    endian, order, resolution, scale = MAGIC[magic]
    major, minor, reserved1, reserved2, snaplen, linktype_word = struct.unpack_from(endian + "HHIIII", data, 4)
    if major != 2:
        raise ValueError(f"unsupported PCAP major version {major}")
    if snaplen == 0:
        raise ValueError("PCAP snapshot length must be nonzero")

    offset = 24
    count = captured_total = original_total = truncated_count = oversized_count = reversed_count = 0
    previous = first = last = earliest = latest = None
    while offset < len(data) and count < max_packets:
        if len(data) - offset < 16:
            raise ValueError(f"truncated packet record header at byte {offset}")
        seconds, fraction, captured, original = struct.unpack_from(endian + "IIII", data, offset)
        if fraction >= scale:
            raise ValueError(f"invalid timestamp fraction in packet {count + 1}")
        end = offset + 16 + captured
        if end > len(data):
            raise ValueError(f"truncated packet data in packet {count + 1}")
        ticks = seconds * scale + fraction
        if first is None:
            first = ticks
        if previous is not None and ticks < previous:
            reversed_count += 1
        previous = last = ticks
        earliest = ticks if earliest is None else min(earliest, ticks)
        latest = ticks if latest is None else max(latest, ticks)
        count += 1
        captured_total += captured
        original_total += original
        truncated_count += captured < original
        oversized_count += captured > snaplen or captured > original
        offset = end

    warnings = []
    if (major, minor) != (2, 4):
        warnings.append("PCAP version differs from 2.4; verify compatibility with another parser")
    if reserved1 or reserved2:
        warnings.append("nonzero reserved file-header field")
    if linktype_word & 0x03FF0000 or linktype_word & 0x08000000:
        warnings.append("nonzero reserved bits in LinkType word")
    if linktype_word & 0xF0000000 and not linktype_word & 0x04000000:
        warnings.append("FCS length bits set without the presence bit")
    if oversized_count:
        warnings.append("some captured lengths exceed SnapLen or original length")
    if reversed_count:
        warnings.append("packet timestamps decrease in file order")
    return {
        "format": "classic-pcap",
        "file_bytes": len(data),
        "endianness": order,
        "timestamp_resolution": resolution,
        "version": f"{major}.{minor}",
        "snapshot_length": snaplen,
        "linktype": linktype_word & 0xFFFF,
        "linktype_word_hex": f"0x{linktype_word:08x}",
        "packets_scanned": count,
        "captured_bytes": captured_total,
        "original_bytes": original_total,
        "capture_truncated_packets": truncated_count,
        "length_inconsistent_packets": oversized_count,
        "timestamp_order_reversals": reversed_count,
        "first_packet_utc": None if first is None else utc_timestamp(first, scale),
        "last_packet_utc": None if last is None else utc_timestamp(last, scale),
        "earliest_packet_utc": None if earliest is None else utc_timestamp(earliest, scale),
        "latest_packet_utc": None if latest is None else utc_timestamp(latest, scale),
        "packet_limit_reached": offset < len(data),
        "warnings": warnings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ + " Classic PCAP only; no payload values, hosts, or ports are printed."
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--max-packets", type=positive, default=100_000,
                        help="scan at most this many packet records (default: 100000)")
    add_byte_limit(parser)
    args = parser.parse_args(argv)
    try:
        emit(summarize(read_bytes(args.file, args.max_bytes), args.max_packets))
    except (OSError, ValueError) as error:
        print(f"PCAP summary failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
