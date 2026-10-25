#!/usr/bin/env python3
"""Report useful local analysis tools without exposing environment variables."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


TOOLS = {
    "python3": ["--version"],
    "file": ["--version"],
    "rg": ["--version"],
    "jq": ["--version"],
    "sqlite3": ["--version"],
    "openssl": ["version"],
    "xxd": ["-h"],
    "strings": ["--version"],
    "tshark": ["--version"],
    "tcpdump": ["--version"],
    "exiftool": ["-ver"],
    "binwalk": ["--version"],
    "yara": ["--version"],
    "john": ["--list=build-info"],
    "hashcat": ["--version"],
    "ffmpeg": ["-version"],
    "magick": ["-version"],
    "zbarimg": ["--version"],
}


def first_line(value: str) -> str:
    for line in value.splitlines():
        if line.strip():
            return line.strip()[:240]
    return ""


def inspect_tool(name: str, version_args: list[str], include_version: bool) -> dict[str, object]:
    path = shutil.which(name)
    record: dict[str, object] = {"name": name, "available": path is not None, "path": path}
    if not path or not include_version:
        return record
    try:
        result = subprocess.run(
            [path, *version_args],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        record["version"] = first_line(result.stdout) or first_line(result.stderr) or "unknown"
    except (OSError, subprocess.TimeoutExpired) as error:
        record["version"] = f"unavailable: {type(error).__name__}"
    return record


def report(include_version: bool = True) -> list[dict[str, object]]:
    return [inspect_tool(name, arguments, include_version) for name, arguments in TOOLS.items()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check common analysis commands. Credentials and environment variables are never printed."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-version", action="store_true", help="only resolve executable paths")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = report(not args.no_version)
    if args.json:
        json.dump(records, sys.stdout, indent=2)
        print()
    else:
        print("available\tname\tpath\tversion")
        for record in records:
            print(
                "\t".join(
                    (
                        "yes" if record["available"] else "no",
                        str(record["name"]),
                        str(record["path"] or ""),
                        str(record.get("version", "")),
                    )
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
