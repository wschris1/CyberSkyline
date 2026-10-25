#!/usr/bin/env python3
"""Convert common forensic timestamp formats to explicit UTC times."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import sys


UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
WEBKIT_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
FORMATS = {
    "unix-s": (UNIX_EPOCH, Decimal(1)),
    "unix-ms": (UNIX_EPOCH, Decimal(1_000)),
    "unix-us": (UNIX_EPOCH, Decimal(1_000_000)),
    "unix-ns": (UNIX_EPOCH, Decimal(1_000_000_000)),
    "webkit-us": (WEBKIT_EPOCH, Decimal(1_000_000)),
}


def convert(value: str, timestamp_format: str) -> str:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"not a number: {value!r}") from error
    if not number.is_finite():
        raise ValueError(f"timestamp must be finite: {value!r}")
    epoch, units_per_second = FORMATS[timestamp_format]
    seconds = number / units_per_second
    whole_seconds = int(seconds)
    microseconds = int((seconds - whole_seconds) * Decimal(1_000_000))
    try:
        result = epoch + timedelta(seconds=whole_seconds, microseconds=microseconds)
    except OverflowError as error:
        raise ValueError(f"timestamp is outside Python's datetime range: {value!r}") from error
    return result.isoformat(timespec="microseconds").replace("+00:00", "Z")


def records(values: list[str], timestamp_format: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    formats = list(FORMATS) if timestamp_format == "auto" else [timestamp_format]
    for value in values:
        for name in formats:
            try:
                utc = convert(value, name)
            except ValueError:
                if timestamp_format == "auto":
                    continue
                raise
            output.append({"input": value, "format": name, "utc": utc})
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an explicitly identified timestamp, or show all plausible interpretations."
    )
    parser.add_argument("values", nargs="*", help="numbers; read newline-delimited values from stdin if omitted")
    parser.add_argument(
        "--format",
        choices=[*FORMATS, "auto"],
        default="auto",
        help="source epoch and unit; auto prints candidates without choosing one",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    values = args.values or [line.strip() for line in sys.stdin if line.strip()]
    if not values:
        print("no timestamps supplied", file=sys.stderr)
        return 2
    try:
        converted = records(values, args.format)
    except ValueError as error:
        print(f"conversion failed: {error}", file=sys.stderr)
        return 1
    if args.json:
        json.dump(converted, sys.stdout, indent=2)
        print()
    else:
        print("input\tformat\tutc")
        for record in converted:
            print(f"{record['input']}\t{record['format']}\t{record['utc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
