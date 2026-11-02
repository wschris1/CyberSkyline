#!/usr/bin/env python3
"""Compare bytes at the same offsets; report differing ranges, including tails."""

from __future__ import annotations

import argparse
from itertools import zip_longest
from pathlib import Path
import sys

if __package__:
    from ._common import add_byte_limit, emit, positive, read_bytes
else:
    from _common import add_byte_limit, emit, positive, read_bytes


def compare(left: bytes, right: bytes, limit: int = 20) -> dict:
    if limit < 1:
        raise ValueError("range limit must be positive")
    ranges, start, count, total_ranges = [], None, 0, 0

    def finish(end):
        nonlocal start, total_ranges
        total_ranges += 1
        if len(ranges) < limit:
            ranges.append({"start": start, "end_exclusive": end,
                           "left_preview_hex": left[start:min(end, start + 16)].hex(),
                           "right_preview_hex": right[start:min(end, start + 16)].hex()})
        start = None

    for offset, (first, second) in enumerate(zip_longest(left, right)):
        if first != second:
            count += 1
            if start is None:
                start = offset
        elif start is not None:
            finish(offset)
    if start is not None:
        finish(max(len(left), len(right)))
    return {"equal": count == 0, "left_bytes": len(left), "right_bytes": len(right),
            "differing_offsets": count, "range_count": total_ranges,
            "ranges": ranges, "truncated": total_ranges > len(ranges)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ + " Exit: 0 equal, 1 different, 2 error.")
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--limit", type=positive, default=20)
    add_byte_limit(parser)
    args = parser.parse_args(argv)
    try:
        result = compare(read_bytes(args.left, args.max_bytes), read_bytes(args.right, args.max_bytes), args.limit)
        emit(result)
        return 0 if result["equal"] else 1
    except (OSError, ValueError) as error:
        print(f"comparison failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
