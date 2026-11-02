#!/usr/bin/env python3
"""Locate embedded file-signature candidates without extracting or executing them."""

from __future__ import annotations

import argparse
import heapq
from itertools import islice
from pathlib import Path
import sys

if __package__:
    from .artifact_inventory import SIGNATURES
    from ._common import add_byte_limit, emit, positive, read_bytes
else:
    from artifact_inventory import SIGNATURES
    from _common import add_byte_limit, emit, positive, read_bytes


def hits(data: bytes, signature: bytes, label: str):
    start = 0
    while (offset := data.find(signature, start)) != -1:
        yield (offset, label, signature.hex())
        start = offset + 1


def scan(data: bytes, limit: int = 100) -> dict:
    if limit < 1:
        raise ValueError("match limit must be positive")
    candidates = heapq.merge(*(hits(data, magic, label) for magic, label in SIGNATURES))
    found = list(islice(candidates, limit + 1))
    return {"file_bytes": len(data), "matches": [
        {"offset": offset, "kind": label, "signature_hex": magic} for offset, label, magic in found[:limit]
    ], "truncated": len(found) > limit, "validated_formats": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", type=Path)
    parser.add_argument("--limit", type=positive, default=100)
    parser.add_argument("--list-signatures", action="store_true")
    add_byte_limit(parser)
    args = parser.parse_args(argv)
    if args.list_signatures:
        emit([{"hex": magic.hex(), "kind": label} for magic, label in SIGNATURES])
        return 0
    if args.file is None:
        parser.error("supply a file or --list-signatures")
    try:
        emit(scan(read_bytes(args.file, args.max_bytes), args.limit))
    except (OSError, ValueError) as error:
        print(f"signature scan failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
