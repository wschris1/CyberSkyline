#!/usr/bin/env python3
"""Perform one explicit decoding step and report a round-trip check."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
from pathlib import Path
import sys
from urllib.parse import unquote_to_bytes


def decode(value: str, encoding: str) -> tuple[bytes, bool | None]:
    compact = "".join(value.split()) if encoding in {"hex", "base64", "base64url"} else value
    if encoding == "hex":
        decoded = bytes.fromhex(compact)
        canonical = decoded.hex()
        return decoded, canonical.lower() == compact.lower()
    if encoding in {"base64", "base64url"}:
        padded = compact + "=" * (-len(compact) % 4)
        altchars = b"-_" if encoding == "base64url" else None
        decoded = base64.b64decode(padded, altchars=altchars, validate=True)
        encoded = base64.b64encode(decoded, altchars=altchars).decode("ascii").rstrip("=")
        return decoded, encoded == compact.rstrip("=")
    if encoding == "url":
        return unquote_to_bytes(value), None
    if encoding == "form":
        return unquote_to_bytes(value.replace("+", " ")), None
    raise ValueError(f"unsupported encoding: {encoding}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decode a known representation. No recursive guessing or automatic transformation is performed."
    )
    parser.add_argument("encoding", choices=("hex", "base64", "base64url", "url", "form"))
    parser.add_argument("value", nargs="?", help="encoded value; stdin if omitted")
    parser.add_argument("--input-file", type=Path, help="read the encoded value from a UTF-8 text file")
    parser.add_argument("--output", type=Path, help="write decoded bytes; otherwise require UTF-8 and print text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.value is not None and args.input_file is not None:
        print("supply a value or --input-file, not both", file=sys.stderr)
        return 2
    try:
        if args.input_file is not None:
            value = args.input_file.read_text(encoding="utf-8")
        elif args.value is not None:
            value = args.value
        else:
            value = sys.stdin.read()
        decoded, round_trip = decode(value, args.encoding)
    except (OSError, UnicodeError, ValueError, binascii.Error) as error:
        print(f"decode failed: {error}", file=sys.stderr)
        return 1

    digest = hashlib.sha256(decoded).hexdigest()
    round_trip_text = "not-applicable" if round_trip is None else str(round_trip).lower()
    print(f"bytes={len(decoded)} sha256={digest} round_trip={round_trip_text}", file=sys.stderr)
    if args.output is not None:
        try:
            with args.output.open("xb") as output:
                output.write(decoded)
        except OSError as error:
            print(f"could not write output: {error}", file=sys.stderr)
            return 1
    else:
        try:
            print(decoded.decode("utf-8"))
        except UnicodeDecodeError:
            print("decoded bytes are not UTF-8; use --output FILE", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
