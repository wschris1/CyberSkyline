#!/usr/bin/env python3
"""Stream and filter existing password candidates by explicit constraints."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import string
import sys
from typing import Iterable


@dataclass(frozen=True)
class Constraints:
    min_length: int = 0
    max_length: int | None = None
    uppercase: int | None = None
    lowercase: int | None = None
    digits: int | None = None
    special: int | None = None
    special_chars: str = string.punctuation + " "
    ascii_only: bool = False


def fits(candidate: str, constraints: Constraints) -> bool:
    if len(candidate) < constraints.min_length:
        return False
    if constraints.max_length is not None and len(candidate) > constraints.max_length:
        return False
    if constraints.ascii_only and not candidate.isascii():
        return False
    counts = {
        "uppercase": sum(character in string.ascii_uppercase for character in candidate),
        "lowercase": sum(character in string.ascii_lowercase for character in candidate),
        "digits": sum(character in string.digits for character in candidate),
        "special": sum(character in constraints.special_chars for character in candidate),
    }
    for name in ("uppercase", "lowercase", "digits", "special"):
        expected = getattr(constraints, name)
        if expected is not None and counts[name] != expected:
            return False
    return True


def candidates(paths: list[Path]) -> Iterable[str]:
    if not paths:
        for line in sys.stdin:
            yield line.rstrip("\r\n")
        return
    for path in paths:
        with path.open(encoding="utf-8", errors="surrogateescape") as handle:
            for line in handle:
                yield line.rstrip("\r\n")


def nonnegative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Filter supplied candidates; this tool does not generate or test passwords."
    )
    parser.add_argument("files", nargs="*", type=Path, help="candidate files; stdin if omitted")
    parser.add_argument("--min-length", type=nonnegative, default=0)
    parser.add_argument("--max-length", type=nonnegative)
    parser.add_argument("--uppercase", type=nonnegative, help="required exact count")
    parser.add_argument("--lowercase", type=nonnegative, help="required exact count")
    parser.add_argument("--digits", type=nonnegative, help="required exact count")
    parser.add_argument("--special", type=nonnegative, help="required exact count")
    parser.add_argument("--special-chars", default=string.punctuation + " ")
    parser.add_argument("--ascii-only", action="store_true")
    parser.add_argument("--deduplicate", action="store_true")
    parser.add_argument("--count-only", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="suppress the stderr summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_length is not None and args.max_length < args.min_length:
        print("max length cannot be less than min length", file=sys.stderr)
        return 2
    constraints = Constraints(
        min_length=args.min_length,
        max_length=args.max_length,
        uppercase=args.uppercase,
        lowercase=args.lowercase,
        digits=args.digits,
        special=args.special,
        special_chars=args.special_chars,
        ascii_only=args.ascii_only,
    )
    seen: set[str] = set()
    read_count = 0
    match_count = 0
    try:
        for candidate in candidates(args.files):
            read_count += 1
            if args.deduplicate:
                if candidate in seen:
                    continue
                seen.add(candidate)
            if not fits(candidate, constraints):
                continue
            match_count += 1
            if not args.count_only:
                print(candidate)
    except OSError as error:
        print(f"could not read candidates: {error}", file=sys.stderr)
        return 1
    if args.count_only:
        print(match_count)
    if not args.quiet:
        print(f"read={read_count} matched={match_count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
