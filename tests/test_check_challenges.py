"""Exercise the public-content check with temporary, synthetic repositories."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import importlib.util

spec = importlib.util.spec_from_file_location(
    "check_challenges", Path(__file__).resolve().parents[1] / ".github/scripts/check_challenges.py"
)
check_challenges = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_challenges)


class ChallengeCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.challenge = self.root / "challenges" / "synthetic"
        self.challenge.mkdir(parents=True)
        (self.challenge / "question.md").write_text("# Synthetic question\n")
        self.guide = self.challenge / "how-to-solve.md"
        self.guide.write_text("# Method\nVerify the evidence privately.\n")

    def check(self):
        stdout, stderr = StringIO(), StringIO()
        with patch.object(check_challenges, "ROOT", self.root):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = check_challenges.main()
        return code, stdout.getvalue() + stderr.getvalue()

    def test_accepts_method_and_nonanswer_format_template(self):
        self.guide.write_text("# Method\nThe format template is SKY-ABCD-####.\n")
        code, output = self.check()
        self.assertEqual(code, 0, output)

    def test_rejects_sky_token_embedded_in_table(self):
        synthetic = "-".join(("SKY", "TEST", "0000"))
        self.guide.write_text(f"# Method\n| Candidate | {synthetic} |\n")
        code, output = self.check()
        self.assertEqual(code, 1)
        self.assertIn("how-to-solve.md:2: platform flag-like text", output)

    def test_rejects_lowercase_sky_token_in_shared_docs(self):
        docs = self.root / "docs"
        docs.mkdir()
        synthetic = "-".join(("sky", "test", "0000"))
        (docs / "notes.md").write_text(f"Recovered text: {synthetic}\n")
        code, output = self.check()
        self.assertEqual(code, 1)
        self.assertIn("docs/notes.md:1: platform flag-like text", output)

    def test_preserves_brace_format_detection(self):
        synthetic = "ctf" + "{" + "synthetic" + "}"
        self.guide.write_text(f"# Method\n{synthetic}\n")
        code, output = self.check()
        self.assertEqual(code, 1)
        self.assertIn("flag-like text", output)

    def test_preserves_direct_answer_line_detection(self):
        self.guide.write_text("# Method\nAnswer: synthetic value\n")
        code, output = self.check()
        self.assertEqual(code, 1)
        self.assertIn("answer line", output)

    def test_requires_both_challenge_files(self):
        self.guide.unlink()
        code, output = self.check()
        self.assertEqual(code, 1)
        self.assertIn("missing how-to-solve.md", output)

    def test_accepts_season_question_without_a_method_file(self):
        question = self.root / "challenges/spring-2026/practice-game/forensics/easy/example-q1.md"
        question.parent.mkdir(parents=True)
        question.write_text("# Example question\nRead the supplied synthetic input.\n")
        code, output = self.check()
        self.assertEqual(code, 0, output)
        self.assertIn("1 imported questions", output)

    def test_rejects_incorrect_import_hierarchy(self):
        question = self.root / "challenges/spring-2026/forensics/easy/example-q1.md"
        question.parent.mkdir(parents=True)
        question.write_text("# Example question\n")
        code, output = self.check()
        self.assertEqual(code, 1)
        self.assertIn("season/type/category/level", output)


if __name__ == "__main__":
    unittest.main()
