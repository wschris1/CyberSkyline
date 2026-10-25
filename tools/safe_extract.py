#!/usr/bin/env python3
"""List or safely extract ZIP and tar archives with conservative limits."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import zipfile


@dataclass(frozen=True)
class Entry:
    name: str
    size: int
    kind: str
    source: object


class UnsafeArchive(ValueError):
    """Raised when an archive violates the extraction policy."""


def normalized_parts(name: str) -> tuple[str, ...]:
    if "\x00" in name:
        raise UnsafeArchive("member name contains NUL")
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise UnsafeArchive(f"unsafe member path: {name!r}")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if not parts:
        raise UnsafeArchive(f"empty member path: {name!r}")
    if len(parts[0]) >= 2 and parts[0][1] == ":":
        raise UnsafeArchive(f"drive-qualified member path: {name!r}")
    return parts


def zip_entries(archive: zipfile.ZipFile) -> list[Entry]:
    entries: list[Entry] = []
    for member in archive.infolist():
        mode = member.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK:
            kind = "symlink"
        elif member.is_dir():
            kind = "directory"
        elif file_type not in (0, stat.S_IFREG):
            kind = "special"
        else:
            kind = "file"
        entries.append(Entry(member.filename, member.file_size, kind, member))
    return entries


def tar_entries(archive: tarfile.TarFile) -> list[Entry]:
    entries: list[Entry] = []
    for member in archive.getmembers():
        if member.isdir():
            kind = "directory"
        elif member.isfile():
            kind = "file"
        elif member.issym():
            kind = "symlink"
        elif member.islnk():
            kind = "hardlink"
        else:
            kind = "special"
        entries.append(Entry(member.name, member.size, kind, member))
    return entries


def validate(entries: list[Entry], max_members: int, max_bytes: int) -> None:
    if len(entries) > max_members:
        raise UnsafeArchive(f"archive has {len(entries)} members; limit is {max_members}")
    total = 0
    names: set[tuple[str, ...]] = set()
    for entry in entries:
        parts = normalized_parts(entry.name)
        if parts in names:
            raise UnsafeArchive(f"duplicate member path: {entry.name!r}")
        names.add(parts)
        if entry.kind not in {"file", "directory"}:
            raise UnsafeArchive(f"unsupported {entry.kind}: {entry.name!r}")
        if entry.size < 0:
            raise UnsafeArchive(f"negative member size: {entry.name!r}")
        total += entry.size
        if total > max_bytes:
            raise UnsafeArchive(f"expanded size exceeds {max_bytes} bytes")


def prepare_destination(destination: Path) -> Path:
    if destination.is_symlink():
        raise UnsafeArchive("destination must not be a symbolic link")
    if destination.exists():
        if not destination.is_dir():
            raise UnsafeArchive("destination exists and is not a directory")
        if any(destination.iterdir()):
            raise UnsafeArchive("destination directory is not empty")
    else:
        destination.mkdir(parents=True)
    return destination.resolve()


def target_for(destination: Path, name: str) -> Path:
    target = destination.joinpath(*normalized_parts(name)).resolve()
    if target != destination and destination not in target.parents:
        raise UnsafeArchive(f"member escapes destination: {name!r}")
    return target


def copy_limited(source, target, expected_size: int) -> None:
    written = 0
    with target.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            written += len(chunk)
            if written > expected_size:
                raise UnsafeArchive(f"member expanded beyond declared size: {target.name!r}")
            output.write(chunk)
    if written != expected_size:
        raise UnsafeArchive(f"member size mismatch: {target.name!r}")


def extract_zip(archive: zipfile.ZipFile, entries: list[Entry], destination: Path) -> None:
    for entry in entries:
        target = target_for(destination, entry.name)
        if entry.kind == "directory":
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(entry.source) as source:
            copy_limited(source, target, entry.size)


def extract_tar(archive: tarfile.TarFile, entries: list[Entry], destination: Path) -> None:
    for entry in entries:
        target = target_for(destination, entry.name)
        if entry.kind == "directory":
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(entry.source)
        if source is None:
            raise UnsafeArchive(f"could not read member: {entry.name!r}")
        with source:
            copy_limited(source, target, entry.size)


def open_archive(path: Path):
    if zipfile.is_zipfile(path):
        archive = zipfile.ZipFile(path)
        return archive, zip_entries(archive), "zip"
    if tarfile.is_tarfile(path):
        archive = tarfile.open(path, mode="r:*")
        return archive, tar_entries(archive), "tar"
    raise UnsafeArchive("supported formats are ZIP and tar archives recognized by Python")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and list an archive, or extract regular files into an empty directory."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--extract", type=Path, metavar="DIRECTORY")
    parser.add_argument("--max-members", type=int, default=10_000)
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    archive = None
    try:
        archive, entries, archive_type = open_archive(args.archive)
        validate(entries, args.max_members, args.max_bytes)
        print(f"type\t{archive_type}")
        print(f"members\t{len(entries)}")
        print(f"expanded_bytes\t{sum(entry.size for entry in entries)}")
        print("kind\tsize\tname")
        for entry in entries:
            escaped_name = json.dumps(entry.name, ensure_ascii=True)[1:-1]
            print(f"{entry.kind}\t{entry.size}\t{escaped_name}")
        if args.extract:
            destination = prepare_destination(args.extract)
            if archive_type == "zip":
                extract_zip(archive, entries, destination)
            else:
                extract_tar(archive, entries, destination)
            print(f"extracted_to\t{destination}")
    except (OSError, tarfile.TarError, zipfile.BadZipFile, UnsafeArchive) as error:
        print(f"archive rejected: {error}", file=sys.stderr)
        return 1
    finally:
        if archive is not None:
            archive.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
