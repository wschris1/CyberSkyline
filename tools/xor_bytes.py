#!/usr/bin/env python3
"""Apply an explicit repeating XOR key and write bytes to a new file."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

if __package__:
    from ._common import add_byte_limit, emit, nonnegative, read_bytes
else:
    from _common import add_byte_limit, emit, nonnegative, read_bytes


def transform(data: bytes, key: bytes, offset: int = 0) -> bytes:
    if not key or offset < 0:
        raise ValueError("key must be nonempty and key offset must be non-negative")
    return bytes(value ^ key[(index + offset) % len(key)] for index, value in enumerate(data))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ + " No key search is performed.")
    parser.add_argument("file", type=Path)
    keys = parser.add_mutually_exclusive_group(required=True)
    keys.add_argument("--key-hex", help="explicit hexadecimal key; prefer --key-file for sensitive keys")
    keys.add_argument("--key-file", type=Path, help="raw key bytes; newlines are part of the key")
    parser.add_argument("--key-offset", type=nonnegative, default=0)
    parser.add_argument("--output", type=Path, required=True, help="new file; never overwritten")
    add_byte_limit(parser)
    args = parser.parse_args(argv)
    try:
        key = read_bytes(args.key_file, 1024 * 1024) if args.key_file else bytes.fromhex(args.key_hex)
        result = transform(read_bytes(args.file, args.max_bytes), key, args.key_offset)
        with args.output.open("xb") as handle:
            handle.write(result)
        emit({"bytes": len(result), "sha256": hashlib.sha256(result).hexdigest(), "key_bytes": len(key)})
    except (OSError, ValueError) as error:
        print(f"XOR failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
