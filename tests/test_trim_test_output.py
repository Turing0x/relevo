"""Black-box tests for hooks/trim-test-output (updatedInput rewrite and the --run wrapper)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "trim-test-output"

MATCH = [
    "make check",
    "make test -j4",
    "pytest -k foo tests/x.py",
    "python3 -m unittest discover -s tests",
    ".venv/bin/python -m pytest -x",
    "uv run pytest",
    "npm test",
    "npm run test",
    "go test ./...",
    "cargo test",
]

NO_MATCH = [
    "make check; ls",
    "make check && make test",
    "pytest | tail",
    "pytest > out.txt",
    "echo $(pytest)",
    "pytest `x`",
    'pytest -k "foo"',
    "pytest -k 'foo'",
    "pytest tests/*.py",
    "pytest ~/x",
    "RELEVO_FULL_OUTPUT=1 make check",
    "make deploy",
    "make check deploy",
    "pytest .env",
    "pytest ../x",
    "npm test -- --watch",
    "git push",
    "git push --force",
    "pytest\nls",
    "",
]


def run_hook(stdin: str, **env: str) -> subprocess.CompletedProcess[str]:
    full = {k: v for k, v in os.environ.items() if k != "RELEVO_TRIM_DISABLE"}
    full.update(env)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=full, timeout=30, check=False
    )


def rewrite(command: str, **env: str) -> subprocess.CompletedProcess[str]:
    return run_hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}), **env)


def wrapper(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK), "--run", "--", *argv],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


class HookModeTests(unittest.TestCase):
    def test_matching_commands_are_rewritten(self) -> None:
        for command in MATCH:
            with self.subTest(command=command):
                result = rewrite(command)
                self.assertEqual(result.returncode, 0)
                output = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual(output["hookEventName"], "PreToolUse")
                self.assertNotIn("permissionDecision", output)
                self.assertEqual(
                    shlex.split(output["updatedInput"]["command"]),
                    [sys.executable, str(HOOK.resolve()), "--run", "--", *command.split()],
                )

    def test_other_commands_produce_no_output(self) -> None:
        for command in NO_MATCH:
            with self.subTest(command=command):
                result = rewrite(command)
                self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_rewritten_command_does_not_match_again(self) -> None:
        command = json.loads(rewrite("make check").stdout)["hookSpecificOutput"]["updatedInput"]["command"]
        self.assertEqual(rewrite(command).stdout, "")

    def test_other_tool_input_fields_are_kept(self) -> None:
        tool_input = {"command": "make check", "timeout": 5000, "description": "d", "run_in_background": True}
        result = run_hook(json.dumps({"tool_input": tool_input}))
        updated = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]
        self.assertEqual(updated, {**tool_input, "command": updated["command"]})

    def test_invalid_input_is_ignored(self) -> None:
        invalid = ("", "{ not json", "[]", "{}", '{"tool_input": "make check"}', '{"tool_input": {"command": 3}}')
        for stdin in invalid:
            with self.subTest(stdin=stdin):
                result = run_hook(stdin)
                self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_disable_variable(self) -> None:
        self.assertEqual(rewrite("make check", RELEVO_TRIM_DISABLE="1").stdout, "")
        self.assertNotEqual(rewrite("make check", RELEVO_TRIM_DISABLE="0").stdout, "")

    def test_hook_is_executable(self) -> None:
        self.assertTrue(HOOK.stat().st_mode & stat.S_IXUSR)


class RunModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env = {**os.environ, "TMPDIR": self._tmp.name}

    def py(self, code: str) -> subprocess.CompletedProcess[str]:
        return wrapper(sys.executable, "-c", code, env=self.env)

    def logs(self) -> list[Path]:
        return sorted(Path(self._tmp.name).glob("relevo-test-*.log"))

    def test_exit_code_is_the_childs(self) -> None:
        for code in (0, 1, 2, 5):
            with self.subTest(code=code):
                self.assertEqual(self.py(f"import sys; sys.exit({code})").returncode, code)

    def test_missing_command_is_127(self) -> None:
        self.assertEqual(wrapper("relevo-no-such-command-xyz", env=self.env).returncode, 127)

    def test_killed_by_signal_is_128_plus_n(self) -> None:
        result = self.py("import os, signal; os.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(result.returncode, 128 + signal.SIGTERM)

    def test_sigint_is_forwarded_and_gives_130(self) -> None:
        proc = subprocess.Popen([sys.executable, str(HOOK), "--run", "--", "sleep", "30"], env=self.env)
        time.sleep(1)
        proc.send_signal(signal.SIGINT)
        self.assertEqual(proc.wait(timeout=10), 130)

    def test_short_output_is_untouched(self) -> None:
        result = self.py("print('\\n'.join(f'l{i}' for i in range(119))); import sys; print('FAIL', file=sys.stderr)")
        self.assertEqual(result.stdout.count("\n"), 120)
        self.assertNotIn("[relevo]", result.stdout)
        self.assertEqual(self.logs(), [])

    def test_long_failing_output_is_trimmed_with_full_log(self) -> None:
        code = "import sys\nfor i in range(500): print(f'line {i}')\nprint('Traceback boom')\nprint('end')\nsys.exit(3)"
        result = self.py(code)
        self.assertEqual(result.returncode, 3)
        self.assertIn("Traceback boom", result.stdout)
        self.assertNotIn("line 100\n", result.stdout)
        self.assertIn("line 499", result.stdout)
        self.assertLess(result.stdout.count("\n"), 130)
        (log,) = self.logs()
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
        self.assertIn(f"[relevo] salida recortada: 502 líneas, exit 3, completa en {log}", result.stdout)
        self.assertEqual(log.read_text(encoding="utf-8").splitlines()[:2], ["line 0", "line 1"])
        self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 502)

    def test_long_successful_output_keeps_only_the_tail(self) -> None:
        result = self.py("for i in range(500): print(f'FAIL-looking {i}')")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count("\n"), 31)
        self.assertIn("FAIL-looking 499", result.stdout)
        self.assertNotIn("FAIL-looking 0\n", result.stdout)

    def test_log_failure_prints_full_output_and_keeps_exit_code(self) -> None:
        module = types.ModuleType("trim_test_output")
        exec(compile(HOOK.read_text(encoding="utf-8"), str(HOOK), "exec"), module.__dict__)
        code = "import sys; print('\\n'.join(map(str, range(300)))); sys.exit(4)"
        out = io.StringIO()
        broken = mock.patch.object(module.tempfile, "mkstemp", side_effect=OSError("disk full"))
        with broken, contextlib.redirect_stdout(out):
            self.assertEqual(module.run([sys.executable, "-c", code]), 4)
        self.assertEqual(out.getvalue().count("\n"), 300)
        self.assertNotIn("[relevo]", out.getvalue())

    def test_old_own_logs_are_pruned(self) -> None:
        old = Path(self._tmp.name) / "relevo-test-old.log"
        recent = Path(self._tmp.name) / "relevo-test-recent.log"
        other = Path(self._tmp.name) / "other-old.log"
        for path in (old, recent, other):
            path.write_text("x", encoding="utf-8")
        stale = time.time() - 25 * 3600
        os.utime(old, (stale, stale))
        os.utime(other, (stale, stale))
        self.py("print('\\n'.join(map(str, range(300))))")
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(other.exists())
        self.assertEqual(len(self.logs()), 2)

    def test_stderr_is_merged(self) -> None:
        result = self.py("import sys; print('to-err', file=sys.stderr)")
        self.assertIn("to-err", result.stdout)


if __name__ == "__main__":
    unittest.main()
