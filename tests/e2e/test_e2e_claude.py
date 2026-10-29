"""End-to-end tests: the real Claude Code CLI against a scripted fake of the Messages API.

relevo is installed into a temporary HOME, ``claude -p`` runs in a temporary git repository with
``ANTHROPIC_BASE_URL`` pointing at ``fake_api.FakeMessagesAPI``, and the scripts make the "model" try a force
push, read ``.env`` or launch workers. The tests check what the real hooks did (the tool results Claude Code
sends back, the telemetry log) and never contact the real API. No API key, no cost.

Opt-in: they run only with ``RELEVO_E2E=1`` and a ``claude`` executable (or ``RELEVO_CLAUDE_BIN``); otherwise
they are skipped. ``make e2e`` sets the variable. See docs/decisions/0011-doctor-y-e2e.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from .fake_api import Error, FakeMessagesAPI, result_text, text, tool, tool_results

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "relevo_install.py"
CLAUDE = os.environ.get("RELEVO_CLAUDE_BIN") or shutil.which("claude")
ENABLED = os.environ.get("RELEVO_E2E") == "1" and CLAUDE is not None
CANARY = "RELEVO-E2E-CANARY-7f3a"
TIMEOUT = 120
LOGBOOK_CANARY = "RELEVO-E2E-LOGBOOK-5c1d"
ORCH_RESUME_BANNER = "relevo orch-resume: tarea activa"
SUBAGENT_STOP_CHANGED = "SubagentStop now fires here: update docs/failure-modes.md and docs/audit-pending.md"


@unittest.skipUnless(ENABLED, "set RELEVO_E2E=1 and install Claude Code (or set RELEVO_CLAUDE_BIN) to run")
class ClaudeCodeE2E(unittest.TestCase):
    api: FakeMessagesAPI

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.home = tmp / "home"
        self.home.mkdir()
        self.log = tmp / "log.jsonl"
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "install"],
            env={"HOME": str(self.home), "PATH": os.environ.get("PATH", "")},
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.repo = tmp / "repo"
        self.remote = tmp / "remote.git"
        git = ["git", "-c", "user.name=e2e", "-c", "user.email=e2e@example.invalid", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        (self.repo / "README").write_text("e2e\n", encoding="utf-8")
        (self.repo / ".env").write_text(f"TOKEN={CANARY}\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(".env\n.claude/work/\n", encoding="utf-8")
        subprocess.run([*git, "-C", str(self.repo), "add", "README", ".gitignore"], check=True)
        subprocess.run([*git, "-C", str(self.repo), "commit", "-q", "-m", "init"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", str(self.remote)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "push", "-q", "origin", "main"], check=True)
        self.api = FakeMessagesAPI().start()
        self.addCleanup(self.api.stop)

    def claude(self, prompt: str, *extra: str) -> subprocess.CompletedProcess[str]:
        assert CLAUDE is not None
        env = {
            "HOME": str(self.home),
            "PATH": os.environ.get("PATH", ""),
            "ANTHROPIC_BASE_URL": self.api.url,
            "ANTHROPIC_API_KEY": "sk-ant-e2e-fake",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
            "ORCH_LOG": str(self.log),
        }
        return subprocess.run(
            [CLAUDE, "-p", prompt, "--output-format", "json", "--max-turns", "6", *extra],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )

    def results(self, marker: str) -> list[str]:
        """Text of every tool_result the conversation ``marker`` sent back, from its last request."""
        conversation = self.api.conversation(marker)
        self.assertTrue(conversation, f"no request reached the fake API for {marker}")
        return [result_text(block) for block in tool_results(conversation[-1].body)]

    def telemetry(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def remote_head(self) -> str:
        return subprocess.run(
            ["git", "-C", str(self.remote), "rev-parse", "main"], capture_output=True, text=True, check=True
        ).stdout.strip()

    def sync_telemetry(self) -> None:
        """Register orch-telemetry without ``async`` in this temporary HOME.

        ``claude -p`` exits as soon as the main conversation ends and an async SubagentStop hook never runs
        (observed with Claude Code 2.1.312; the interactive CLI is not covered here). The test needs the record.
        """
        path = self.home / ".claude" / "settings.json"
        settings = json.loads(path.read_text(encoding="utf-8"))
        for group in settings["hooks"]["SubagentStop"]:
            for hook in group["hooks"]:
                if hook["command"].endswith("orch-telemetry"):
                    hook.pop("async", None)
        path.write_text(json.dumps(settings), encoding="utf-8")

    def records(self, agent_name: str) -> list[dict[str, Any]]:
        return [r for r in self.telemetry() if r.get("agent") == agent_name]

    def only_session_start(self, matcher: str) -> None:
        """Keep only the orch-resume group for ``matcher`` in this temporary HOME, to tell the two apart."""
        path = self.home / ".claude" / "settings.json"
        settings = json.loads(path.read_text(encoding="utf-8"))
        settings["hooks"]["SessionStart"] = [g for g in settings["hooks"]["SessionStart"] if g["matcher"] == matcher]
        self.assertEqual(len(settings["hooks"]["SessionStart"]), 1)
        path.write_text(json.dumps(settings), encoding="utf-8")

    def start_session_with_logbook(self) -> str:
        self.api.scripts["E2E-LOGBOOK"] = [text("vale")] * 10
        first = self.claude("E2E-LOGBOOK empieza")
        self.assertEqual(first.returncode, 0, first.stderr)
        session: str = json.loads(first.stdout)["session_id"]
        task = self.repo / ".claude" / "work" / "login"
        task.mkdir(parents=True)
        (task / "estado.md").write_text(f"petición: e2e\nciclos: 1/2\n{LOGBOOK_CANARY}\n", encoding="utf-8")
        return session

    def logbook_in(self, requests: list[Any]) -> bool:
        return any(LOGBOOK_CANARY in json.dumps(r.body) and ORCH_RESUME_BANNER in json.dumps(r.body) for r in requests)

    # ------------------------------------------------------------------ hooks on the main session

    def test_force_push_is_blocked_by_the_hook(self) -> None:
        before = self.remote_head()
        self.api.scripts["E2E-PUSH"] = [
            tool("Bash", {"command": "git push --force origin HEAD:main", "description": "push"}),
            text("hecho"),
        ]
        self.claude("E2E-PUSH haz push")
        results = self.results("E2E-PUSH")
        self.assertEqual(len(results), 1)
        self.assertIn("bloqueado por", results[0])
        self.assertIn("block-force-push", results[0])
        self.assertEqual(self.remote_head(), before)

    def test_secrets_never_reach_the_model(self) -> None:
        self.api.scripts["E2E-ENV"] = [
            tool("Read", {"file_path": str(self.repo / ".env")}),
            tool("Bash", {"command": "cat .env", "description": "leer"}),
            tool("Grep", {"pattern": "TOKEN", "path": str(self.repo), "output_mode": "content"}),
            text("hecho"),
        ]
        self.claude("E2E-ENV lee el .env")
        results = self.results("E2E-ENV")
        self.assertEqual(len(results), 3)
        self.assertIn("guard-secrets", results[1])
        self.assertNotIn(CANARY, self.api.raw_bodies())

    # ------------------------------------------------------------------ SessionStart: orch-resume (audit-pending #8)

    def test_logbook_reaches_the_context_on_resume(self) -> None:
        self.only_session_start("resume")
        session = self.start_session_with_logbook()
        self.assertFalse(self.logbook_in(self.api.requests))
        before = len(self.api.requests)
        self.claude("sigue", "--resume", session)
        self.assertTrue(self.logbook_in(self.api.requests[before:]))

    def test_logbook_reaches_the_context_after_compact(self) -> None:
        self.only_session_start("compact")
        session = self.start_session_with_logbook()
        compacted = json.loads(self.claude("/compact", "--resume", session).stdout)
        self.assertFalse(self.logbook_in(self.api.requests))  # the resume group is gone: nothing yet
        before = len(self.api.requests)
        self.claude("sigue", "--resume", compacted.get("session_id", session))
        self.assertTrue(self.logbook_in(self.api.requests[before:]))

    # ------------------------------------------------------------------ workers and SubagentStop

    def test_worker_report_is_logged_by_orch_telemetry(self) -> None:
        self.sync_telemetry()
        self.api.scripts["E2E-MAIN"] = [
            agent({"prompt": "E2E-RAPIDO lista archivos", "subagent_type": "rapido"}),
            text("hecho"),
        ]
        self.api.scripts["E2E-RAPIDO"] = [text("ESTADO: OK\nResultado: README\nRiesgo: ninguno")]
        self.claude("E2E-MAIN delega")
        self.assertTrue(self.api.conversation("E2E-RAPIDO"), "the worker never called the API")
        records = self.records("rapido")
        self.assertEqual(len(records), 1, self.telemetry())
        self.assertEqual(records[0]["status"], "OK")
        self.assertTrue(str(records[0]["model"]).startswith("claude-haiku"), records[0])
        self.assertIn("ESTADO: OK", "\n".join(self.results("E2E-MAIN")))

    def test_explore_override_runs_on_haiku_with_low_effort(self) -> None:
        # audit-pending #1 and #3: the relevo Explore replaces the built-in one, with its model and effort.
        self.sync_telemetry()
        self.api.scripts["E2E-MAIN"] = [
            agent({"prompt": "E2E-EXPLORE busca", "subagent_type": "Explore"}),
            text("hecho"),
        ]
        self.api.scripts["E2E-EXPLORE"] = [text("ESTADO: OK")]
        self.claude("E2E-MAIN delega")
        sub = self.api.conversation("E2E-EXPLORE")
        self.assertTrue(sub, "the worker never called the API")
        self.assertTrue(all(str(r.body.get("model")).startswith("claude-haiku") for r in sub))
        records = self.records("Explore")
        self.assertEqual(len(records), 1, self.telemetry())
        self.assertEqual(records[0]["effort"], "low")

    def test_spawn_depth_one_hides_the_agent_tool_from_workers(self) -> None:
        # audit-pending #4: general-purpose has no disallowedTools, so only the depth limit can hide the tool.
        self.api.scripts["E2E-MAIN"] = [
            agent({"prompt": "E2E-GP delega", "subagent_type": "general-purpose"}),
            text("hecho"),
        ]
        self.api.scripts["E2E-GP"] = [text("ESTADO: OK")]
        self.claude("E2E-MAIN delega")
        main_tools = {t.get("name") for t in self.api.conversation("E2E-MAIN")[0].body.get("tools", [])}
        self.assertIn("Agent", main_tools)
        sub = self.api.conversation("E2E-GP")
        self.assertTrue(sub, "the worker never called the API")
        for request in sub:
            names = {t.get("name") for t in request.body.get("tools", [])}
            self.assertFalse(names & {"Agent", "Task"}, sorted(names))

    def test_worker_hitting_max_turns_returns_to_the_router(self) -> None:
        # audit-pending #2: clasificador has maxTurns 3 and the script never lets it finish on its own.
        self.sync_telemetry()
        self.api.scripts["E2E-MAIN"] = [
            agent({"prompt": "E2E-CLASIF clasifica", "subagent_type": "clasificador"}),
            text("hecho"),
        ]
        self.api.scripts["E2E-CLASIF"] = [tool("Glob", {"pattern": "*"})] * 20
        self.claude("E2E-MAIN delega")
        self.assertEqual(len(self.api.conversation("E2E-CLASIF")), 3)
        report = "\n".join(self.results("E2E-MAIN"))
        self.observe("maxTurns", report)
        self.assertNotIn("ESTADO", report)
        # Observed with 2.1.312: a worker stopped by maxTurns does not fire SubagentStop, so orch-telemetry
        # writes nothing and the "tope" column of /orch-stats cannot count it (docs/failure-modes.md).
        self.assertEqual(self.records("clasificador"), [], SUBAGENT_STOP_CHANGED)

    def test_worker_api_error_returns_to_the_router(self) -> None:
        # audit-pending #5: the worker's first request fails with a non-retryable error.
        self.sync_telemetry()
        self.api.scripts["E2E-MAIN"] = [agent({"prompt": "E2E-FALLA lista", "subagent_type": "rapido"}), text("hecho")]
        self.api.scripts["E2E-FALLA"] = [Error(400)] * 5
        result = self.claude("E2E-MAIN delega")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = "\n".join(self.results("E2E-MAIN"))
        self.observe("error", report)
        self.assertIn("400", report)
        self.assertEqual(self.api.conversation("E2E-MAIN")[-1].turn, 1)
        self.assertEqual(self.records("rapido"), [], SUBAGENT_STOP_CHANGED)

    def observe(self, label: str, value: str) -> None:
        if os.environ.get("RELEVO_E2E_VERBOSE") == "1":
            print(f"\n[{self._testMethodName}] {label}: {value[:1500]}", file=sys.stderr)


def agent(tool_input: dict[str, Any]) -> list[dict[str, Any]]:
    """An Agent tool call in the foreground, so that ``claude -p`` waits for the worker and its SubagentStop."""
    return tool("Agent", {"description": "e2e", "run_in_background": False, **tool_input})


if __name__ == "__main__":
    unittest.main()
