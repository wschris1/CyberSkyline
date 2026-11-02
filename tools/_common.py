"""Shared bounded file reads and CLI value checks for offline helpers."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat


DEFAULT_MAX_BYTES = 32 * 1024 * 1024


def nonnegative(value: str) -> int:
    try:
        result = int(value, 16 if value.lower().startswith("0x") else 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use a decimal integer or 0x-prefixed hex") from error
    if result < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return result


def positive(value: str) -> int:
    result = nonnegative(value)
    if result == 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return result


def open_regular(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be an existing regular file, not a symbolic link")
    handle = path.open("rb")
    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
        handle.close()
        raise ValueError("input is not a regular file")
    return handle


def read_bytes(path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    if max_bytes <= 0:
        raise ValueError("byte limit must be positive")
    with open_regular(path) as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"input exceeds {max_bytes} bytes; raise --max-bytes deliberately")
    return data


def add_byte_limit(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-bytes", type=positive, default=DEFAULT_MAX_BYTES,
                        help="input byte limit (default: 32 MiB per file)")


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False))
