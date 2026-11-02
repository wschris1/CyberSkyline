#!/usr/bin/env python3
"""Display a bounded byte range with absolute offsets, hex, and printable ASCII."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__:
    from ._common import emit, nonnegative, open_regular, positive
else:
    from _common import emit, nonnegative, open_regular, positive


def rows(data: bytes, offset: int = 0, width: int = 16) -> list[dict]:
    if offset < 0 or not 1 <= width <= 64:
        raise ValueError("offset must be non-negative and width must be 1..64")
    return [{"offset": offset + start, "hex": data[start:start + width].hex(" "),
             "ascii": "".join(chr(byte) if 32 <= byte <= 126 else "."
                              for byte in data[start:start + width])}
            for start in range(0, len(data), width)]


def view(path: Path, offset: int, length: int, width: int = 16) -> dict:
    if offset < 0 or not 1 <= length <= 1024 * 1024:
        raise ValueError("offset must be non-negative and length must be 1..1048576")
    with open_regular(path) as handle:
        size = handle.seek(0, 2)
        if offset > size:
            raise ValueError("offset is past the end of the file")
        handle.seek(offset)
        data = handle.read(length)
    return {"file_bytes": size, "shown_bytes": len(data), "offset": offset,
            "more_bytes": offset + len(data) < size, "rows": rows(data, offset, width)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--offset", type=nonnegative, default=0)
    parser.add_argument("--length", type=positive, default=256, help="bytes to show; maximum 1 MiB")
    parser.add_argument("--width", type=positive, default=16)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = view(args.file, args.offset, args.length, args.width)
        if args.json:
            emit(result)
        else:
            for row in result["rows"]:
                print(f"{row['offset']:08x}  {row['hex']:<{args.width * 3 - 1}}  |{row['ascii']}|")
            print(f"shown={result['shown_bytes']} file_bytes={result['file_bytes']} more={result['more_bytes']}",
                  file=sys.stderr)
    except (OSError, ValueError) as error:
        print(f"hex view failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
