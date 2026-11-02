"""Keep the public navigation aligned with the files that actually exist."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = (
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "challenges.md",
    ROOT / "tools" / "README.md",
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
CHALLENGE_LINK = re.compile(
    r"\]\(\.\./challenges/([^/]+)/(question|how-to-solve)\.md\)"
)


def required_count(pattern: str, text: str, source: str) -> int:
    match = re.search(pattern, text)
    if match is None:
        raise AssertionError(f"{source}: expected count label is missing")
    return int(match.group(1))


class RepositoryNavigationTests(unittest.TestCase):
    def test_readme_counts_match_repository(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        tool_catalog = (ROOT / "tools" / "README.md").read_text(encoding="utf-8")
        skill_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        challenge_index = (ROOT / "docs" / "challenges.md").read_text(encoding="utf-8")

        challenges = {
            path.name for path in (ROOT / "challenges").iterdir()
            if path.is_dir() and path.name != "_template"
        }
        tools = {
            path.name for path in (ROOT / "tools").glob("*.py")
            if not path.name.startswith("_")
        }
        playbooks = set((ROOT / "docs" / "skills").glob("*.md"))

        self.assertEqual(required_count(r"Explore (\d+) challenges", readme, "README"), len(challenges))
        self.assertEqual(required_count(r"Use (\d+) tools", readme, "README"), len(tools))
        self.assertEqual(required_count(r"Read (\d+) playbooks", readme, "README"), len(playbooks))
        self.assertEqual(required_count(r"\*\*(\d+) command-line helpers", tool_catalog, "tool catalog"), len(tools))
        self.assertEqual(required_count(r"\[(\d+)-tool catalog\]", skill_index, "skill index"), len(tools))
        self.assertEqual(required_count(r"Explore (\d+) challenge prompts", challenge_index, "challenge index"), len(challenges))

    def test_challenge_index_lists_each_pair_once(self) -> None:
        index = (ROOT / "docs" / "challenges.md").read_text(encoding="utf-8")
        actual = {
            path.name for path in (ROOT / "challenges").iterdir()
            if path.is_dir() and path.name != "_template"
        }
        links = CHALLENGE_LINK.findall(index)
        expected = {(slug, kind) for slug in actual for kind in ("question", "how-to-solve")}
        self.assertEqual(set(links), expected)
        self.assertEqual(len(links), len(expected), "challenge index contains duplicate links")
        for slug in actual:
            for name in ("question.md", "how-to-solve.md"):
                self.assertTrue((ROOT / "challenges" / slug / name).is_file())

    def test_navigation_links_resolve_within_repository(self) -> None:
        for document in NAVIGATION:
            text = document.read_text(encoding="utf-8")
            for raw in MARKDOWN_LINK.findall(text):
                target = raw.strip("<>").split("#", 1)[0].split("?", 1)[0]
                if not target:
                    continue
                parsed = urlsplit(target)
                if parsed.scheme or target.startswith("//"):
                    continue
                with self.subTest(document=str(document.relative_to(ROOT)), link=raw):
                    resolved = (document.parent / unquote(target)).resolve()
                    self.assertTrue(resolved.is_relative_to(ROOT.resolve()))
                    self.assertTrue(resolved.exists(), f"missing local link: {raw}")

    def test_readme_banner_exists(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r'<img\s+src="(assets/[^"]+\.svg)"', readme)
        self.assertIsNotNone(match, "README banner link is missing")
        self.assertTrue((ROOT / match.group(1)).is_file())


if __name__ == "__main__":
    unittest.main()
