#!/usr/bin/env python3
"""Check a plain RSA or Ed25519 OpenSSH public-key blob and report its SHA-256 fingerprint."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
from pathlib import Path
import sys

if __package__:
    from ._common import emit, read_bytes
else:
    from _common import emit, read_bytes


def read_string(blob: bytes, offset: int):
    if offset + 4 > len(blob):
        raise ValueError("truncated SSH length field")
    length = int.from_bytes(blob[offset:offset + 4], "big")
    end = offset + 4 + length
    if end > len(blob):
        raise ValueError("truncated SSH string")
    return blob[offset + 4:end], end


def positive_mpint(value: bytes) -> int:
    if not value or value[0] & 0x80 or (value[0] == 0 and (len(value) == 1 or not value[1] & 0x80)):
        raise ValueError("RSA parameter must be a canonical positive SSH mpint")
    return int.from_bytes(value, "big")


def inspect(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("supply one plain OpenSSH public key, without authorized_keys options")
    parts = lines[0].split(None, 2)
    if len(parts) < 2 or parts[0] not in {"ssh-rsa", "ssh-ed25519"}:
        raise ValueError("supported plain public key types: ssh-rsa, ssh-ed25519")
    blob = base64.b64decode(parts[1], validate=True)
    algorithm, offset = read_string(blob, 0)
    if algorithm != parts[0].encode("ascii"):
        raise ValueError("outer key type does not match the embedded key type")
    if parts[0] == "ssh-ed25519":
        key, offset = read_string(blob, offset)
        if len(key) != 32:
            raise ValueError("Ed25519 public key must contain exactly 32 bytes")
        bits = 256
    else:
        exponent, offset = read_string(blob, offset)
        modulus, offset = read_string(blob, offset)
        e, n = positive_mpint(exponent), positive_mpint(modulus)
        if e <= 1 or e % 2 == 0 or n <= e or n % 2 == 0:
            raise ValueError("invalid basic RSA parameter structure")
        bits = n.bit_length()
    if offset != len(blob):
        raise ValueError("unexpected trailing bytes in SSH key blob")
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return {"key_type": parts[0], "key_bits": bits, "blob_bytes": len(blob),
            "fingerprint": "SHA256:" + fingerprint, "validation": "structure only"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ + " Does not verify ownership, signatures, or cryptographic strength.")
    parser.add_argument("file", type=Path, help="public key file, maximum 64 KiB; comments are not printed")
    args = parser.parse_args(argv)
    try:
        emit(inspect(read_bytes(args.file, 65536).decode("utf-8")))
    except (OSError, ValueError, UnicodeError, binascii.Error) as error:
        print(f"public-key inspection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
