#!/usr/bin/env python3
"""Read bounded EXIF tags from JPEG, TIFF and PNG without decoding image pixels."""

import argparse
import json
from pathlib import Path
import struct
import sys
import zlib


TAGS = {0x010F: 'Make', 0x0110: 'Model', 0x0131: 'Software', 0x0132: 'DateTime',
        0x9003: 'DateTimeOriginal', 0x9004: 'DateTimeDigitized',
        0x9010: 'OffsetTime', 0x9011: 'OffsetTimeOriginal', 0x9012: 'OffsetTimeDigitized',
        0xA002: 'PixelXDimension', 0xA003: 'PixelYDimension', 0xA431: 'BodySerialNumber',
        0xA434: 'LensModel'}
GPS_TAGS = {1: 'GPSLatitudeRef', 2: 'GPSLatitude', 3: 'GPSLongitudeRef',
            4: 'GPSLongitude', 7: 'GPSTimeStamp', 29: 'GPSDateStamp'}
LIMIT = 64 * 1024 * 1024


def tiff_tags(data, base=0):
    if len(data) < 8 or data[:2] not in (b'II', b'MM'):
        raise ValueError('Invalid TIFF byte order/header')
    endian = '<' if data[:2] == b'II' else '>'

    def read(fmt, offset):
        size = struct.calcsize(endian + fmt)
        if offset < 0 or offset + size > len(data):
            raise ValueError('TIFF offset outside metadata')
        return struct.unpack_from(endian + fmt, data, offset)

    if read('H', 2)[0] != 42:
        raise ValueError('Unsupported TIFF format')
    pending = [(read('I', 4)[0], False)]
    visited, output = set(), []
    while pending:
        offset, gps = pending.pop(0)
        if not offset:
            continue
        if offset in visited or len(visited) >= 8:
            raise ValueError('Repeated or excessive EXIF directories')
        visited.add(offset)
        count = read('H', offset)[0]
        if count > 256:
            raise ValueError('EXIF directory exceeds tag limit')
        read('I', offset + 2 + 12 * count)  # Validate the complete table.
        for i in range(count):
            entry = offset + 2 + 12 * i
            tag, kind, length = read('HHI', entry)
            if not gps and tag in (0x8769, 0x8825):
                if kind != 4 or length != 1:
                    raise ValueError('Invalid EXIF directory pointer')
                pending.append((read('I', entry + 8)[0], tag == 0x8825))
                continue
            name = (GPS_TAGS if gps else TAGS).get(tag)
            if not name:
                continue
            width = {2: 1, 3: 2, 4: 4, 5: 8}.get(kind)
            if width is None or not 1 <= length <= 4096:
                raise ValueError('Unsupported or excessive EXIF value')
            size = width * length
            start = entry + 8 if size <= 4 else read('I', entry + 8)[0]
            if start + size > len(data):
                raise ValueError('Truncated EXIF value')
            raw = data[start:start + size]
            if kind == 2:
                value = raw.rstrip(b'\0').decode('ascii')
                if any(ord(c) < 32 or ord(c) > 126 for c in value):
                    raise ValueError('Invalid EXIF text')
            elif kind in (3, 4):
                numbers = read(('H' if kind == 3 else 'I') * length, start)
                value = numbers[0] if length == 1 else list(numbers)
            else:
                value = []
                for j in range(length):
                    numerator, denominator = read('II', start + j * 8)
                    if not denominator:
                        raise ValueError('Invalid EXIF rational')
                    value.append([numerator, denominator])
            output.append(dict(tag=name, value=value, offset=base + start))
        # IFD1 is a thumbnail and must not be mistaken for the original image.
    return output


def inspect(data):
    if len(data) > LIMIT:
        raise ValueError('Image exceeds metadata limit')
    blocks, kind = [], None
    if data[:2] in (b'II', b'MM'):
        kind, blocks = 'TIFF', [(data, 0)]
    elif data.startswith(b'\xff\xd8'):
        kind, pos = 'JPEG', 2
        while pos < len(data):
            if data[pos] != 255:
                raise ValueError('Invalid JPEG marker')
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data):
                raise ValueError('Truncated JPEG marker')
            marker = data[pos]
            pos += 1
            if marker in (0xDA, 0xD9):
                break
            if marker == 1 or 0xD0 <= marker <= 0xD7:
                continue
            if pos + 2 > len(data):
                raise ValueError('Truncated JPEG segment')
            length = int.from_bytes(data[pos:pos + 2], 'big')
            if length < 2 or pos + length > len(data):
                raise ValueError('Invalid JPEG segment size')
            if marker == 0xE1 and data[pos + 2:pos + 8] == b'Exif\0\0':
                blocks.append((data[pos + 8:pos + length], pos + 8))
            pos += length
    elif data.startswith(b'\x89PNG\r\n\x1a\n'):
        kind, pos = 'PNG', 8
        while pos < len(data):
            if pos + 12 > len(data):
                raise ValueError('Truncated PNG chunk')
            length = int.from_bytes(data[pos:pos + 4], 'big')
            end = pos + 12 + length
            if end > len(data):
                raise ValueError('Invalid PNG chunk size')
            chunk = data[pos + 4:pos + 8]
            if chunk == b'eXIf':
                crc = int.from_bytes(data[end - 4:end], 'big')
                if zlib.crc32(data[pos + 4:end - 4]) & 0xFFFFFFFF != crc:
                    raise ValueError('Invalid EXIF chunk checksum')
                blocks.append((data[pos + 8:end - 4], pos + 8))
            pos = end
            if chunk == b'IEND':
                break
    else:
        raise ValueError('Supported metadata formats are JPEG, TIFF and PNG')
    if len(blocks) > 8:
        raise ValueError('Too many EXIF blocks')
    tags = [item for block, base in blocks for item in tiff_tags(block, base)]
    return dict(format=kind, tags=tags, exif_blocks=len(blocks),
                limits='Embedded metadata only; not proof of camera clock accuracy or unmodified pixels. '
                       'No filesystem dates, XMP, maker notes or thumbnail metadata are interpreted.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.file.is_symlink() or not args.file.is_file() or args.file.stat().st_size > LIMIT:
            raise ValueError('Expected a regular image file of at most 64 MiB')
        print(json.dumps(inspect(args.file.read_bytes()), ensure_ascii=False, indent=2))
    except (OSError, ValueError, UnicodeError) as exc:
        print(f'Metadata inspection failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
