#!/usr/bin/env python3
"""Summarize JSON Lines schemas and optionally count an explicitly selected field."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

if __package__:
    from ._common import emit, open_regular, positive
else:
    from _common import emit, open_regular, positive


def reject_constant(value):
    raise ValueError("non-finite JSON number")


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number exceeds finite float range")
    return number


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def kind(value):
    return {dict: "object", list: "array", str: "string", int: "number",
            float: "number", bool: "boolean", type(None): "null"}[type(value)]


def summarize(stream, field=None, max_lines=100_000, max_line_bytes=1024 * 1024, max_groups=1000) -> dict:
    if min(max_lines, max_line_bytes, max_groups) < 1:
        raise ValueError("limits must be positive")
    types, keys, groups = Counter(), {}, Counter()
    total, valid, blank, missing, nonscalar = 0, 0, 0, 0, 0
    invalid, invalid_count = [], 0
    while total < max_lines:
        line = stream.readline(max_line_bytes + 1)
        if not line:
            break
        total += 1
        if len(line) > max_line_bytes:
            raise ValueError(f"line {total} exceeds --max-line-bytes")
        if not line.strip():
            blank += 1
            continue
        try:
            value = json.loads(line.decode("utf-8"), parse_constant=reject_constant,
                               parse_float=finite_float, object_pairs_hook=unique_object)
        except (UnicodeError, ValueError, RecursionError):
            invalid_count += 1
            if len(invalid) < 20:
                invalid.append(total)
            continue
        valid += 1
        types[kind(value)] += 1
        if not isinstance(value, dict):
            if field is not None:
                missing += 1
            continue
        for key, item in value.items():
            if key not in keys:
                if len(keys) >= max_groups:
                    raise ValueError("distinct key limit exceeded; raise --max-groups deliberately")
                keys[key] = Counter()
            keys[key][kind(item)] += 1
        if field is not None:
            if field not in value:
                missing += 1
            elif isinstance(value[field], (dict, list)):
                nonscalar += 1
            else:
                encoded = json.dumps(value[field], ensure_ascii=True, allow_nan=False)
                if encoded not in groups and len(groups) >= max_groups:
                    raise ValueError("distinct value limit exceeded; raise --max-groups deliberately")
                groups[encoded] += 1
    result = {"lines_read": total, "valid_records": valid, "blank_lines": blank,
              "invalid_records": invalid_count, "invalid_line_numbers_first_20": invalid,
              "record_types": dict(types), "keys": {key: dict(keys[key]) for key in sorted(keys)},
              "truncated": bool(stream.read(1))}
    if field is not None:
        result["field_counts"] = {"field": field, "missing": missing, "non_scalar": nonscalar,
                                  "values": [{"value": json.loads(value), "count": count}
                                             for value, count in groups.most_common()]}
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ + " Invalid records are counted and cause exit 1.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--field", help="literal top-level key, including dots; prints its scalar values")
    parser.add_argument("--max-lines", type=positive, default=100_000)
    parser.add_argument("--max-line-bytes", type=positive, default=1024 * 1024)
    parser.add_argument("--max-groups", type=positive, default=1000)
    args = parser.parse_args(argv)
    try:
        with open_regular(args.file) as stream:
            result = summarize(stream, args.field, args.max_lines, args.max_line_bytes, args.max_groups)
        emit(result)
        return 1 if result["invalid_records"] else 0
    except (OSError, ValueError) as error:
        print(f"JSONL summary failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
