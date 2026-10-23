#!/usr/bin/env python3
"""Check the public challenge layout and catch common answer leaks."""

from collections import defaultdict
from pathlib import Path
import os
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FILES = {"question.md", "how-to-solve.md"}
ALLOWED_FILES = REQUIRED_FILES | {"question.png"}
UPLOAD_IMAGE_SIGNATURES = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),
}
PRIVATE_NAME = re.compile(r"^(?:answers?|flags?)(?:[._-]|$)", re.IGNORECASE)
FLAG_TEXT = re.compile(rb"\b(?:flag|ctf|cyberskyline)\{[^}\r\n]+\}", re.IGNORECASE)
ANSWER_LINE = re.compile(
    rb"^[ \t]*(?:final[ \t]+)?(?:answer|flag)[ \t]*[:=][ \t]*\S+",
    re.IGNORECASE | re.MULTILINE,
)


def main() -> int:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    names = sorted({os.fsdecode(name) for name in listed.stdout.split(b"\0") if name})
    challenge_files: dict[str, set[str]] = defaultdict(set)
    problems: list[str] = []

    for name in names:
        path = Path(name)
        if PRIVATE_NAME.match(path.name):
            problems.append(f"{name}: private answer or flag filename")

        if path.parts[0] == "challenges":
            if len(path.parts) != 3:
                problems.append(f"{name}: expected challenges/<name>/<file>")
            else:
                challenge_files[path.parts[1]].add(path.parts[2])

        data = (ROOT / path).read_bytes()
        if path.parts[0] == "IMAGES" and path.name != ".gitkeep":
            if len(path.parts) != 2:
                problems.append(f"{name}: expected a file directly in IMAGES/")
            elif path.suffix.lower() in UPLOAD_IMAGE_SIGNATURES:
                signatures = UPLOAD_IMAGE_SIGNATURES[path.suffix.lower()]
                if not any(data.startswith(sig) for sig in signatures):
                    problems.append(f"{name}: invalid image signature")
                elif path.suffix.lower() == ".webp" and data[8:12] != b"WEBP":
                    problems.append(f"{name}: invalid WebP image")
                continue
            elif path.suffix.lower() != ".txt":
                problems.append(f"{name}: expected an image or plain-text challenge input")
        if path.parts[0] == "challenges" and path.name == "question.png":
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                problems.append(f"{name}: question.png is not a PNG image")
            continue
        if b"\0" in data:
            problems.append(f"{name}: binary files are not allowed")
            continue
        for pattern, label in ((FLAG_TEXT, "flag-like text"), (ANSWER_LINE, "answer line")):
            match = pattern.search(data)
            if match:
                line = data.count(b"\n", 0, match.start()) + 1
                problems.append(f"{name}:{line}: {label} found")

    for challenge, files in sorted(challenge_files.items()):
        for missing in sorted(REQUIRED_FILES - files):
            problems.append(f"challenges/{challenge}: missing {missing}")
        for extra in sorted(files - ALLOWED_FILES):
            problems.append(f"challenges/{challenge}: unexpected {extra}")

    if problems:
        print("Challenge check failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    count = len(challenge_files) - ("_template" in challenge_files)
    print(f"Challenge check passed ({count} published challenges).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
