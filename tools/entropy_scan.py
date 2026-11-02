#!/usr/bin/env python3
"""Measure byte-frequency Shannon entropy by window; do not infer encryption."""

from __future__ import annotations

import argparse
from collections import Counter
import math
from pathlib import Path
import sys

if __package__:
    from ._common import add_byte_limit, emit, positive, read_bytes
else:
    from _common import add_byte_limit, emit, positive, read_bytes


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    size = len(data)
    return -sum((count / size) * math.log2(count / size) for count in Counter(data).values())


def scan(data: bytes, window: int = 4096, step: int | None = None, limit: int = 4096) -> dict:
    step = window if step is None else step
    if min(window, step, limit) < 1:
        raise ValueError("window, step, and limit must be positive")
    starts = range(0, len(data), step)
    result = []
    for start in starts[:limit]:
        block = data[start:start + window]
        result.append({"offset": start, "bytes": len(block),
                       "entropy_bits_per_byte": round(entropy(block), 6)})
    return {"file_bytes": len(data), "window": window, "step": step, "windows": result,
            "truncated": len(starts) > limit}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--window", type=positive, default=4096)
    parser.add_argument("--step", type=positive, help="default: same as window")
    parser.add_argument("--limit", type=positive, default=4096)
    add_byte_limit(parser)
    args = parser.parse_args(argv)
    try:
        emit(scan(read_bytes(args.file, args.max_bytes), args.window, args.step, args.limit))
    except (OSError, ValueError) as error:
        print(f"entropy scan failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
