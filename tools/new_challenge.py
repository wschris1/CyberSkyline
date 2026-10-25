#!/usr/bin/env python3
"""Create a challenge question and method-only guide from the repository template."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


QUESTION = """# {title}

## Question

[Copy the exact player-facing prompt, constraints, scoring, and required response formats here. Remove this guidance before publishing.]
"""


GUIDE = """# {title}: how to solve

## Approach

[Explain why the method fits the supplied evidence. Separate facts from assumptions.]

## Inputs and tools

[List separately obtained artifacts and relevant tool versions. Keep response-bearing material outside this repository.]

## Steps

1. [Describe initial signature and metadata checks performed on preserved originals.]
2. [Document the reproduced method with descriptive placeholders for response-bearing values.]
3. [Label alternatives that were suggested but not run.]

## Check your work

[Describe independent verification against the original evidence without recording the response.]

## Limits and next steps

[State incomplete work, search coverage, assumptions, and the next bounded experiment.]

Before publishing, follow the [CTF playbook](../../docs/ctf-playbook.md), run the repository checks, and manually inspect the full staged diff.
"""


def valid_slug(slug: str) -> bool:
    return bool(SLUG.fullmatch(slug)) and slug != "_template"


def create_challenge(root: Path, slug: str, title: str, dry_run: bool = False) -> Path:
    if not valid_slug(slug):
        raise ValueError("slug must contain lowercase letters, digits, and single hyphens")
    if not title.strip() or "\n" in title or "\r" in title:
        raise ValueError("title must be a nonempty single line")
    destination = root / "challenges" / slug
    if destination.exists():
        raise FileExistsError(destination)
    if dry_run:
        return destination
    destination.mkdir(parents=False)
    (destination / "question.md").write_text(QUESTION.format(title=title), encoding="utf-8")
    (destination / "how-to-solve.md").write_text(GUIDE.format(title=title), encoding="utf-8")
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an answer-free challenge skeleton without overwriting files.")
    parser.add_argument("slug", help="lowercase-hyphenated directory name")
    parser.add_argument("title", help="display title")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        destination = create_challenge(args.root, args.slug, args.title, args.dry_run)
    except (OSError, ValueError) as error:
        print(f"could not create challenge: {error}", file=sys.stderr)
        return 1
    action = "would create" if args.dry_run else "created"
    print(f"{action} {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
