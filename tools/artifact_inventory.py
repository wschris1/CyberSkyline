#!/usr/bin/env python3
"""Inventory artifacts without interpreting or modifying their contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Iterable


SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    (b"RIFF", "RIFF container"),
    (b"%PDF-", "PDF document"),
    (b"PK\x03\x04", "ZIP archive or ZIP-based document"),
    (b"\x1f\x8b", "gzip stream"),
    (b"BZh", "bzip2 stream"),
    (b"\xfd7zXZ\x00", "XZ stream"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!\x1a\x07", "RAR archive"),
    (b"SQLite format 3\x00", "SQLite database"),
    (b"\x7fELF", "ELF executable"),
    (b"MZ", "PE or DOS executable"),
    (b"\xd4\xc3\xb2\xa1", "PCAP capture, little-endian"),
    (b"\xa1\xb2\xc3\xd4", "PCAP capture, big-endian"),
    (b"\x0a\x0d\x0d\x0a", "PCAPNG capture"),
)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def identify(path: Path) -> str:
    with path.open("rb") as handle:
        header = handle.read(16)
    for signature, description in SIGNATURES:
        if header.startswith(signature):
            if description == "RIFF container" and header[8:12] == b"WEBP":
                return "WebP image"
            return description
    if not header:
        return "empty file"
    if b"\x00" not in header:
        return "text or unknown binary"
    return "unknown binary"


def walk_inputs(paths: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for supplied in paths:
        if not supplied.exists() and not supplied.is_symlink():
            raise FileNotFoundError(supplied)
        candidates = [supplied]
        if supplied.is_dir() and not supplied.is_symlink():
            candidates = sorted(supplied.rglob("*"))
        for candidate in candidates:
            absolute = candidate.absolute()
            if absolute in seen or candidate.is_dir():
                continue
            seen.add(absolute)
            yield candidate


def display_path(path: Path, relative_to: Path | None) -> str:
    if relative_to is None:
        return os.fspath(path)
    try:
        return os.fspath(path.absolute().relative_to(relative_to.absolute()))
    except ValueError:
        return os.fspath(path.absolute())


def inventory(paths: Iterable[Path], relative_to: Path | None = None) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in walk_inputs(paths):
        shown = display_path(path, relative_to)
        if path.is_symlink():
            records.append(
                {
                    "path": shown,
                    "size": None,
                    "sha256": None,
                    "kind": "symbolic link (not followed)",
                }
            )
            continue
        records.append(
            {
                "path": shown,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "kind": identify(path),
            }
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List sizes, SHA-256 hashes, and signature-based types. Symlinks are not followed."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="files or directories to inventory")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of TSV")
    parser.add_argument(
        "--relative-to",
        type=Path,
        help="show paths relative to this directory when possible",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        records = inventory(args.paths, args.relative_to)
    except (OSError, ValueError) as error:
        print(f"inventory failed: {error}", file=sys.stderr)
        return 1

    if args.json:
        json.dump(records, sys.stdout, indent=2)
        print()
    else:
        print("path\tsize\tsha256\tkind")
        for record in records:
            values = (record["path"], record["size"], record["sha256"], record["kind"])
            print("\t".join("-" if value is None else str(value) for value in values))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
