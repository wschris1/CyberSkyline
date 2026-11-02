#!/usr/bin/env python3
"""Locate printable ASCII strings and ASCII-range UTF-16 strings with offsets."""

from __future__ import annotations

import argparse
import heapq
from itertools import islice
from pathlib import Path
import re
import sys

if __package__:
    from ._common import add_byte_limit, emit, positive, read_bytes
else:
    from _common import add_byte_limit, emit, positive, read_bytes


PATTERNS = {"ascii": rb"[\x20-\x7e]", "utf-16le": rb"[\x20-\x7e]\x00",
            "utf-16be": rb"\x00[\x20-\x7e]"}


def matches(data: bytes, encoding: str, minimum: int):
    pattern = re.compile(b"(?:" + PATTERNS[encoding] + b"){" + str(minimum).encode() + b",}")
    for match in pattern.finditer(data):
        yield (match.start(), encoding, match.group().decode(encoding))


def extract(data: bytes, minimum: int = 4, encoding: str = "all", limit: int = 200) -> dict:
    if not 1 <= minimum <= 4096 or limit < 1:
        raise ValueError("minimum must be 1..4096 and limit must be positive")
    encodings = list(PATTERNS) if encoding == "all" else [encoding]
    if any(item not in PATTERNS for item in encodings):
        raise ValueError("unknown encoding")
    found = list(islice(heapq.merge(*(matches(data, name, minimum) for name in encodings)), limit + 1))
    return {"strings": [{"offset": offset, "encoding": name, "text": value}
                        for offset, name, value in found[:limit]], "truncated": len(found) > limit}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--minimum", type=positive, default=4)
    parser.add_argument("--encoding", choices=["all", *PATTERNS], default="all")
    parser.add_argument("--limit", type=positive, default=200)
    add_byte_limit(parser)
    args = parser.parse_args(argv)
    try:
        emit(extract(read_bytes(args.file, args.max_bytes), args.minimum, args.encoding, args.limit))
    except (OSError, ValueError) as error:
        print(f"string extraction failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
