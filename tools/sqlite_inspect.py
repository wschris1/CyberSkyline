#!/usr/bin/env python3
"""Inspect a copied SQLite database through a read-only connection and bounded SELECTs."""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path
import sqlite3
import sys

if __package__:
    from ._common import emit, positive
else:
    from _common import emit, positive


def authorize(action, first, second, database, source):
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if (second or "").lower() in {"load_extension", "readfile", "writefile"} else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def cell(value):
    if isinstance(value, bytes):
        return {"type": "blob", "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, str) and len(value) > 512:
        return {"type": "text", "characters": len(value), "preview": value[:512], "truncated": True}
    if isinstance(value, float) and not math.isfinite(value):
        return {"type": "float", "value": str(value)}
    return value


def inspect(path: Path, statement: str | None = None, limit: int = 50, budget: int = 1_000_000) -> dict:
    if not 1 <= limit <= 1000 or budget < 1000:
        raise ValueError("row limit must be 1..1000; VM budget must be at least 1000")
    if path.is_symlink() or not path.is_file():
        raise ValueError("database must be an existing regular file, not a symbolic link")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        if hasattr(connection, "setlimit"):
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
            connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 64 * 1024)
        connection.set_authorizer(authorize)
        remaining = budget

        def progress():
            nonlocal remaining
            remaining -= 1000
            return 1 if remaining <= 0 else 0

        connection.set_progress_handler(progress, 1000)
        sql = statement if statement is not None else (
            "SELECT type, name, tbl_name FROM sqlite_master ORDER BY type, name"
        )
        cursor = connection.execute(sql)
        records = cursor.fetchmany(limit + 1)
        return {"columns": [entry[0] for entry in cursor.description or []],
                "rows": [[cell(value) for value in row] for row in records[:limit]],
                "truncated": len(records) > limit, "read_only": True}
    finally:
        connection.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ + " Defaults to schema names; keep WAL/journals with the copy.")
    parser.add_argument("database", type=Path)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--table", help="preview a table with quoted identifier handling")
    selection.add_argument("--query", help="single SELECT; writes, ATTACH, PRAGMA, and extension loading are denied")
    parser.add_argument("--limit", type=positive, default=50, help="maximum rows to display (1..1000)")
    parser.add_argument("--vm-budget", type=positive, default=1_000_000, help="approximate SQLite opcode budget")
    args = parser.parse_args(argv)
    statement = args.query
    if args.table is not None:
        statement = 'SELECT * FROM "' + args.table.replace('"', '""') + '"'
    try:
        emit(inspect(args.database, statement, args.limit, args.vm_budget))
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"SQLite inspection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
