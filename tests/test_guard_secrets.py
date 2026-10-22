"""Black-box tests for hooks/guard-secrets (JSON ``ask`` decision or no output; always exit 0)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "guard-secrets"

BASH_ASK = [
    "cat .env",
    "cat .env.local",
    "source .env",
    "cat .env.production",
    "cat ~/.ssh/id_rsa",
    "cat ~/.aws/credentials",
    'bash -c "cat .env"',
    "eval cat .env",
    "python3 -c \"open('.env')\"",
    "node -e \"require('fs').readFileSync('.env')\"",
    "node --env-file=.env app.js",
    "cat<.env",
    "F=.env; cat $F",
    "cat server.pem",
    "cat ~/.netrc",
    "cat .envrc",
]

BASH_QUIET = [
    "cat .env.example",
    "cat .env.sample",
    "cat .env.local.example",
    "grep -r foo --exclude=.env .",
    "cat docs/environment.md",
    "printenv",
    "ls -la",
]

READ_ASK = ["/x/.env", "/home/u/.ssh/id_ed25519", "/x/credentials.json", "/x/key.pem"]
READ_QUIET = ["/x/src/env.py", "/x/.env.example", "/x/README.md"]

GREP_ASK: list[dict[str, str]] = [
    {"pattern": "x", "path": ".env"},
    {"pattern": "x", "glob": "*.env"},
    {"pattern": "x", "glob": "*.{env,pem}"},
    {"pattern": "x", "glob": "{.env,.env.local}"},
]
GREP_QUIET: list[dict[str, str]] = [
    {"pattern": "x", "glob": "!.env"},
    {"pattern": "x", "glob": "*.py"},
    {"pattern": "x", "path": "src"},
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


def run_tool(tool: str, tool_input: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return run_hook(json.dumps({"tool_name": tool, "tool_input": tool_input}))


class GuardSecretsTests(unittest.TestCase):
    def assert_ask(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        output = payload["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "ask")
        self.assertTrue(output["permissionDecisionReason"])

    def assert_quiet(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_bash_asks(self) -> None:
        for command in BASH_ASK:
            with self.subTest(command=command):
                self.assert_ask(run_tool("Bash", {"command": command}))

    def test_bash_quiet(self) -> None:
        for command in BASH_QUIET:
            with self.subTest(command=command):
                self.assert_quiet(run_tool("Bash", {"command": command}))

    def test_read_asks(self) -> None:
        for path in READ_ASK:
            with self.subTest(path=path):
                self.assert_ask(run_tool("Read", {"file_path": path}))

    def test_read_quiet(self) -> None:
        for path in READ_QUIET:
            with self.subTest(path=path):
                self.assert_quiet(run_tool("Read", {"file_path": path}))

    def test_grep_asks(self) -> None:
        for tool_input in GREP_ASK:
            with self.subTest(tool_input=tool_input):
                self.assert_ask(run_tool("Grep", tool_input))

    def test_grep_quiet(self) -> None:
        for tool_input in GREP_QUIET:
            with self.subTest(tool_input=tool_input):
                self.assert_quiet(run_tool("Grep", tool_input))

    def test_glob_tool_is_not_inspected(self) -> None:
        self.assert_quiet(run_tool("Glob", {"pattern": "**/.env"}))

    def test_invalid_json_is_quiet(self) -> None:
        self.assert_quiet(run_hook("this is not json"))
        self.assert_quiet(run_hook(""))


if __name__ == "__main__":
    unittest.main()
