#!/usr/bin/env python3
"""Extract URLs from text while redacting query values by default."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


URL_PATTERN = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
TRAILING = ".,;:!?)]}"


def find_urls(text: str) -> list[str]:
    return [match.group(0).rstrip(TRAILING) for match in URL_PATTERN.finditer(text)]


def analyze(url: str, include_values: bool = False) -> dict[str, object]:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError:
        port = None
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    keys = [key for key, _ in pairs]
    if include_values:
        shown = url
    else:
        redacted_query = urlencode([(key, "[redacted]") for key, _ in pairs])
        host = (parsed.hostname or "").lower()
        display_host = f"[{host}]" if ":" in host else host
        if parsed.username is not None:
            authority = "[userinfo]@" + display_host
        else:
            authority = display_host
        if port is not None:
            authority += f":{port}"
        shown = urlunsplit((parsed.scheme.lower(), authority, parsed.path, redacted_query, ""))
    return {
        "url": shown,
        "scheme": parsed.scheme.lower(),
        "host": (parsed.hostname or "").lower(),
        "port": port,
        "path": parsed.path,
        "query_keys": keys,
        "has_fragment": bool(parsed.fragment),
    }


def inventory(texts: list[str], include_values: bool = False) -> list[dict[str, object]]:
    counts = Counter(url for text in texts for url in find_urls(text))
    output: list[dict[str, object]] = []
    for url in sorted(counts):
        record = analyze(url, include_values)
        record["count"] = counts[url]
        output.append(record)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract and summarize HTTP(S) URLs. Query values and fragments are hidden by default."
    )
    parser.add_argument("files", nargs="*", type=Path, help="UTF-8 text files; stdin if omitted")
    parser.add_argument("--include-values", action="store_true", help="show original query values and fragments")
    parser.add_argument("--hosts-only", action="store_true", help="print unique hosts only")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        texts = [path.read_text(encoding="utf-8", errors="replace") for path in args.files]
    except OSError as error:
        print(f"could not read input: {error}", file=sys.stderr)
        return 1
    if not texts:
        texts = [sys.stdin.read()]
    records = inventory(texts, args.include_values)
    if args.hosts_only:
        for host in sorted({str(record["host"]) for record in records if record["host"]}):
            print(host)
    elif args.json:
        json.dump(records, sys.stdout, indent=2)
        print()
    else:
        print("count\tscheme\thost\tport\tpath\tquery_keys\turl")
        for record in records:
            fields = (
                record["count"],
                record["scheme"],
                record["host"],
                "" if record["port"] is None else record["port"],
                record["path"],
                ",".join(record["query_keys"]),
                record["url"],
            )
            print("\t".join(str(field) for field in fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
