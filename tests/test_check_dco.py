"""Tests for scripts/check_dco.py using throwaway git repositories."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_dco.py"

AUTHOR = "dev@example.com"
DEPENDABOT = "49699333+dependabot[bot]@users.noreply.github.com"
ACTIONS_BOT = "41898282+github-actions[bot]@users.noreply.github.com"


class DcoTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "ORCH_LOG": str(self.home / "log.jsonl"),
        }
        self.git("init", "-q", "-b", "main")
        self.git("commit", "-q", "--allow-empty", "-m", "chore: root", "-s")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args: str, email: str = AUTHOR, name: str = "Dev") -> str:
        cmd = ["git", "-c", f"user.name={name}", "-c", f"user.email={email}", *args]
        result = subprocess.run(cmd, cwd=self.repo, env=self.env, capture_output=True, text=True, check=True)
        return result.stdout

    def commit(self, message: str, *, sign: bool, author: str | None = None, email: str = AUTHOR) -> None:
        args = ["commit", "-q", "--allow-empty", "-m", message]
        if sign:
            args.append("-s")
        if author:
            args.append(f"--author={author}")
        self.git(*args, email=email)

    def check(self, base: str | None = None, head: str = "HEAD") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), base or self.base, head],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_signed_commit_passes(self) -> None:
        self.commit("feat: signed", sign=True)
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unsigned_commit_fails_with_instructions(self) -> None:
        self.commit("feat: unsigned subject", sign=False)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("feat: unsigned subject", result.stdout)
        self.assertIn("git commit --amend -s", result.stdout)
        self.assertIn("git rebase --signoff origin/main", result.stdout)

    def test_signoff_email_must_match_author(self) -> None:
        # Committer (and so the sign-off) is dev@example.com, author is someone else.
        self.commit("fix: other author", sign=True, author="Other <other@example.com>")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("fix: other author", result.stdout)

    def test_email_comparison_ignores_case(self) -> None:
        self.commit("fix: mixed case", sign=True, author="Dev <DEV@Example.com>")
        self.assertEqual(self.check().returncode, 0)

    def test_one_bad_commit_among_good_ones_fails(self) -> None:
        self.commit("feat: good one", sign=True)
        self.commit("feat: bad one", sign=False)
        self.commit("feat: good two", sign=True)
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("feat: bad one", result.stdout)
        self.assertNotIn("feat: good", result.stdout)

    def test_merge_commits_are_ignored(self) -> None:
        self.git("checkout", "-q", "-b", "topic")
        self.commit("feat: topic work", sign=True)
        self.git("checkout", "-q", "main")
        self.commit("feat: main work", sign=True)
        self.git("merge", "-q", "--no-ff", "-m", "Merge branch 'topic'", "topic")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_bot_emails_are_exempt(self) -> None:
        self.commit("chore(deps): bump", sign=False, author=f"dependabot[bot] <{DEPENDABOT}>")
        self.commit("chore: automated", sign=False, author=f"github-actions[bot] <{ACTIONS_BOT}>")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_lookalike_bot_email_is_not_exempt(self) -> None:
        self.commit("chore: spoof", sign=False, author="dependabot[bot] <dependabot[bot]@users.noreply.github.com>")
        self.assertEqual(self.check().returncode, 1)

    def test_empty_range_passes(self) -> None:
        self.assertEqual(self.check(head=self.base).returncode, 0)

    def test_unknown_revision_fails(self) -> None:
        result = self.check(base="does-not-exist")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.strip())

    def test_usage_error(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
