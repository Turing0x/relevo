"""Black-box tests for hooks/block-force-push (exit 2 blocks, exit 0 allows)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "block-force-push"

BLOCKED = [
    "git push --force",
    "git push -f",
    "git push origin main --force",
    "git push origin main -f",
    "git push --force-with-lease",
    "git -C /tmp/some/dir push -f",
    "git -c user.name=x push --force",
    "git --no-pager push -f",
    "git push origin +main",
    "git push origin :feature",
    "git push origin --delete feature",
    "git push -d origin feature",
    "git push --mirror",
    'bash -c "git push -f"',
    "sh -c 'git push -f'",
    'zsh -c "git push -f"',
    "echo hi && git push -f",
    "(git push -f)",
    "echo $(git push -f)",
    "/usr/bin/git push -f",
]

ALLOWED = [
    "git push",
    "git push origin main",
    "git fetch --force",
    'echo "git push -f"',
    "git push -u origin main",
    "git push --follow-tags",
    "git push --dry-run",
    'git commit -m "push -f"',
    "git push origin HEAD:refs/heads/x",
    "git pull -f",
]


def run_hook(stdin: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        env["HOME"] = tmp
        env["ORCH_LOG"] = os.path.join(tmp, "log.jsonl")
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )


def run_command(command: str) -> subprocess.CompletedProcess[str]:
    return run_hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}))


class BlockForcePushTests(unittest.TestCase):
    def test_blocked_commands(self) -> None:
        for command in BLOCKED:
            with self.subTest(command=command):
                result = run_command(command)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(result.stderr.strip(), "a block must explain itself on stderr")

    def test_allowed_commands(self) -> None:
        for command in ALLOWED:
            with self.subTest(command=command):
                result = run_command(command)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_invalid_input_never_blocks(self) -> None:
        for stdin in ("not json at all", "{}", "", '{"tool_input": null}'):
            with self.subTest(stdin=stdin):
                self.assertEqual(run_hook(stdin).returncode, 0)


class KnownGapTests(unittest.TestCase):
    """Documented limitations: see SECURITY.md#ai-orchestrator-specific-risks.

    These commands SHOULD be blocked but are not. If a test starts passing, the hook got
    better: remove the decorator and move the command to BLOCKED.
    """

    @unittest.expectedFailure
    def test_variable_indirection(self) -> None:
        self.assertEqual(run_command("G=git; $G push -f").returncode, 2)

    @unittest.expectedFailure
    def test_git_alias(self) -> None:
        self.assertEqual(run_command("git -c alias.pf='push -f' pf").returncode, 2)

    @unittest.expectedFailure
    def test_eval_with_quoted_argument(self) -> None:
        self.assertEqual(run_command('eval "git push -f"').returncode, 2)


if __name__ == "__main__":
    unittest.main()
