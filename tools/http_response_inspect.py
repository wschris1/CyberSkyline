#!/usr/bin/env python3
"""Inspect a saved HTTP/1.x response; no requests, decompression, or chunk decoding."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys

if __package__:
    from ._common import add_byte_limit, emit, read_bytes
else:
    from _common import add_byte_limit, emit, read_bytes


TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
STATUS = re.compile(rb"HTTP/(1\.[01]) ([1-5][0-9]{2})(?: [\x20-\x7e\x80-\xff]*)?\Z")


def header_block(data: bytes, start: int):
    match = re.search(rb"\r\n\r\n|\n\n", data[start:start + 65540])
    if match is None or match.start() > 65536:
        raise ValueError("missing header terminator or header block exceeds 64 KiB")
    raw = data[start:start + match.start()]
    separator = b"\r\n" if match.group() == b"\r\n\r\n" else b"\n"
    lines = raw.split(separator)
    status = STATUS.fullmatch(lines[0])
    if status is None:
        raise ValueError("expected an HTTP/1.0 or HTTP/1.1 status line")
    headers = []
    for line in lines[1:]:
        if line.startswith((b" ", b"\t")):
            raise ValueError("obsolete folded header encountered; preserve and inspect manually")
        name, colon, value = line.partition(b":")
        if not colon or TOKEN.fullmatch(name) is None:
            raise ValueError("malformed header name or missing colon")
        if any(byte < 32 and byte != 9 or byte == 127 for byte in value):
            raise ValueError("control byte in header value")
        headers.append((name.decode("ascii"), value.strip(b" \t").decode("latin-1")))
    return status.group(1).decode(), int(status.group(2)), headers, start + match.end(), separator == b"\n"


def inspect(data: bytes, show_values: bool = False, request_method: str = "GET", headers_only: bool = False) -> dict:
    start, interim, warnings = 0, [], []
    for _ in range(17):
        version, status, headers, start, bare_lf = header_block(data, start)
        if bare_lf:
            warnings.append("LF-only header lines; preserved capture may not contain wire CRLFs")
        if 100 <= status < 200 and status != 101:
            interim.append(status)
            continue
        break
    else:
        raise ValueError("too many informational responses")
    body = data[start:]
    lengths = [part.strip() for name, value in headers if name.lower() == "content-length" for part in value.split(",")]
    transfer = [value for name, value in headers if name.lower() == "transfer-encoding"]
    declared = None
    if lengths:
        if any(not re.fullmatch(r"[0-9]+", value) or len(value) > 20 for value in lengths):
            warnings.append("invalid Content-Length")
        elif len({int(value) for value in lengths}) != 1:
            warnings.append("conflicting Content-Length values")
        else:
            declared = int(lengths[0])
    if transfer:
        warnings.append("Transfer-Encoding present; raw trailing bytes are not a decoded body")
        if lengths:
            warnings.append("both Transfer-Encoding and Content-Length are present")
    no_body = request_method.upper() == "HEAD" or status in {101, 204, 304}
    tunnel = request_method.upper() == "CONNECT" and 200 <= status < 300
    if not (headers_only or no_body or tunnel or transfer) and declared is not None and declared != len(body):
        warnings.append("captured trailing byte count differs from Content-Length")
    if no_body and body:
        warnings.append("trailing bytes after a response with no HTTP message body")
    if tunnel:
        warnings.append("successful CONNECT: trailing bytes belong to a tunnel")
    return {"version": version, "status": status, "informational_statuses": interim,
            "headers": [{"name": name, "value": value if show_values else "[redacted]"} for name, value in headers],
            "declared_content_length": declared, "trailing_bytes": len(body),
            "trailing_sha256": hashlib.sha256(body).hexdigest(), "warnings": warnings}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ + " Header values are hidden unless requested.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--show-values", action="store_true", help="print all header values, potentially including secrets")
    parser.add_argument("--request-method", choices=["GET", "POST", "HEAD", "CONNECT", "OTHER"], default="GET")
    parser.add_argument("--headers-only", action="store_true", help="capture intentionally excludes the body")
    add_byte_limit(parser)
    args = parser.parse_args(argv)
    try:
        emit(inspect(read_bytes(args.file, args.max_bytes), args.show_values, args.request_method, args.headers_only))
    except (OSError, ValueError) as error:
        print(f"HTTP inspection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
