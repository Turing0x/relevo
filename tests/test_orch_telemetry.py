"""Black-box tests for hooks/orch-telemetry (SubagentStop hook that appends one line to ORCH_LOG)."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "orch-telemetry"
SCHEMA = ROOT / "docs" / "contracts" / "telemetry-record.schema.json"

TEXT = "x" * 40
HANDBACK_INPUT = {"message": "ESTADO: OK\nArchivos: ninguno"}


def assistant(
    msg_id: str,
    timestamp: str,
    usage: dict[str, int],
    content: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "effort": "low",
        "message": {"id": msg_id, "model": "claude-haiku-5-5", "usage": usage, "content": content},
    }


def write_transcript(path: Path, extra_text: str = TEXT, handback: bool = True) -> None:
    """Message m1 streams over three lines (growing usage); m2 calls SubagentHandback."""
    text_block = {"type": "text", "text": extra_text}
    rows: list[Any] = [
        {"type": "user", "timestamp": "2026-10-22T10:00:00.000Z", "message": {"content": "brief"}},
        assistant("m1", "2026-10-22T10:00:01.000Z", {"input_tokens": 10, "cache_read_input_tokens": 100}, []),
        "this line is not JSON",
        assistant(
            "m1",
            "2026-10-22T10:00:02.000Z",
            {"input_tokens": 12, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 5},
            [text_block],
        ),
        assistant(
            "m1",
            "2026-10-22T10:00:03.000Z",
            {"input_tokens": 12, "cache_read_input_tokens": 110, "cache_creation_input_tokens": 5},
            [text_block],
        ),
    ]
    if handback:
        block = {"type": "tool_use", "id": "t1", "name": "SubagentHandback", "input": HANDBACK_INPUT}
        rows.append(assistant("m2", "2026-10-22T10:00:42.000Z", {"input_tokens": 20}, [block]))
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write((row if isinstance(row, str) else json.dumps(row)) + "\n")


class TelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.log = self.tmp / "log.jsonl"
        self.transcript = self.tmp / "transcript.jsonl"

    def sleep_shim(self, append_on_call: int = 0, line: str = "") -> Path:
        """sitecustomize that replaces time.sleep: it records each call (no real wait) and, on call
        number append_on_call, appends line to the transcript. Returns the file with the calls."""
        shim = self.tmp / "shim"
        shim.mkdir(exist_ok=True)
        calls = self.tmp / "sleeps.txt"
        (shim / "sitecustomize.py").write_text(
            "import time\n"
            f"CALLS, TRANSCRIPT, AT, LINE = {str(calls)!r}, {str(self.transcript)!r}, {append_on_call}, {line!r}\n"
            "def fake_sleep(seconds):\n"
            "    with open(CALLS, 'a') as f:\n"
            "        f.write(repr(seconds) + '\\n')\n"
            "    if AT and len(open(CALLS).read().splitlines()) == AT:\n"
            "        with open(TRANSCRIPT, 'a') as f:\n"
            "            f.write(LINE)\n"
            "time.sleep = fake_sleep\n",
            encoding="utf-8",
        )
        self.shim = shim
        return calls

    def run_hook(
        self, payload: dict[str, Any], log: Path | None = None, retry_delay: str = "0"
    ) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        env["ORCH_TELEMETRY_RETRY_DELAY"] = retry_delay  # 0 keeps the suite fast
        if getattr(self, "shim", None):
            env["PYTHONPATH"] = str(self.shim)
        env["HOME"] = str(self.tmp)
        env["ORCH_LOG"] = str(log or self.log)
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
            check=False,
        )

    def payload(self, last_message: str | None = "ESTADO: OK") -> dict[str, Any]:
        return {
            "agent_type": "rapido",
            "agent_id": "agent-1",
            "session_id": "session-1",
            "cwd": str(self.tmp),
            "agent_transcript_path": str(self.transcript),
            "last_assistant_message": last_message,
        }

    def records(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_record_fields(self) -> None:
        write_transcript(self.transcript)
        result = self.run_hook(self.payload())
        self.assertEqual(result.returncode, 0)
        records = self.records()
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["agent"], "rapido")
        self.assertEqual(rec["agent_id"], "agent-1")
        self.assertEqual(rec["session"], "session-1")
        self.assertEqual(rec["model"], "claude-haiku-5-5")
        self.assertEqual(rec["effort"], "low")
        self.assertEqual(rec["turns"], 2)  # m1 and m2, however many lines each one took
        self.assertEqual(rec["in"], 12 + 20)  # sum over ids of the max per id
        self.assertEqual(rec["cache_read"], 110)
        self.assertEqual(rec["cache_write"], 5)
        self.assertEqual(rec["out_est"], (len(TEXT) + len(json.dumps(HANDBACK_INPUT, ensure_ascii=False))) // 4)
        self.assertEqual(rec["dur_s"], 42)
        self.assertEqual(rec["status"], "OK")

    def test_one_line_per_run(self) -> None:
        write_transcript(self.transcript)
        self.run_hook(self.payload())
        self.run_hook(self.payload())
        self.assertEqual(len(self.records()), 2)

    def test_status_variants(self) -> None:
        write_transcript(self.transcript, handback=False)
        cases = {
            "ESTADO: OK": "OK",
            "VEREDICTO: RECHAZADO\nCausa: diseño": "RECHAZADO",
            "estado: escalar: demasiado grande": "ESCALAR",
            '{"tipo": "implementacion", "riesgo": "bajo"}': "JSON",
            "just some prose": "SIN_ESTADO",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                if self.log.exists():
                    self.log.unlink()
                self.run_hook(self.payload(message))
                self.assertEqual(self.records()[0]["status"], expected)

    def test_status_falls_back_to_transcript(self) -> None:
        write_transcript(self.transcript)  # the handback message carries ESTADO: OK
        self.run_hook(self.payload("no status line here"))
        self.assertEqual(self.records()[0]["status"], "OK")

    def test_status_recovered_when_handback_is_flushed_late(self) -> None:
        write_transcript(self.transcript, handback=False)  # hook starts before the SubagentHandback line exists
        block = {"type": "tool_use", "id": "t1", "name": "SubagentHandback", "input": HANDBACK_INPUT}
        line = json.dumps(assistant("m2", "2026-10-22T10:00:42.000Z", {"input_tokens": 20}, [block])) + "\n"
        calls = self.sleep_shim(append_on_call=2, line=line)  # the line shows up during the 2nd wait
        result = self.run_hook(self.payload(""))
        self.assertEqual(result.returncode, 0)
        rec = self.records()[0]
        self.assertEqual(rec["status"], "OK")
        self.assertEqual(rec["turns"], 2)  # the summary is recomputed on the successful read
        self.assertEqual(rec["in"], 12 + 20)
        self.assertEqual(len(calls.read_text(encoding="utf-8").splitlines()), 2)  # stops retrying once found

    def test_sin_estado_after_retries_when_status_never_appears(self) -> None:
        write_transcript(self.transcript, handback=False)
        calls = self.sleep_shim()
        result = self.run_hook(self.payload(""))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.records()[0]["status"], "SIN_ESTADO")
        self.assertEqual(len(calls.read_text(encoding="utf-8").splitlines()), 5)  # 5 re-reads, then give up

    def test_no_retry_when_status_already_present(self) -> None:
        write_transcript(self.transcript, handback=False)
        calls = self.sleep_shim()
        self.run_hook(self.payload("ESTADO: OK"))
        self.assertEqual(self.records()[0]["status"], "OK")
        self.assertFalse(calls.exists())  # time.sleep never called

    def test_invalid_retry_delay_never_loses_the_record(self) -> None:
        write_transcript(self.transcript, handback=False)
        calls = self.sleep_shim()
        # Negative clamps to 0; non-numeric, non-finite and huge values fall back to or cap at 0.5 s.
        cases = {"-1": 0.0, "abc": 0.5, "nan": 0.5, "inf": 0.5, "1e308": 0.5, "1e6": 0.5}
        for value, expected in cases.items():
            with self.subTest(value=value):
                for f in (self.log, calls):
                    if f.exists():
                        f.unlink()
                result = self.run_hook(self.payload(""), retry_delay=value)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, "")
                self.assertEqual(len(self.records()), 1)
                self.assertEqual(self.records()[0]["status"], "SIN_ESTADO")
                waits = [float(s) for s in calls.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(waits, [expected] * 5)  # 5 re-reads, each wait capped at 0.5 s

    def test_nothing_written_without_agent_type(self) -> None:
        write_transcript(self.transcript)
        payload = self.payload()
        del payload["agent_type"]
        result = self.run_hook(payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.records(), [])

    def test_nothing_written_without_transcript(self) -> None:
        payload = self.payload()
        payload["agent_transcript_path"] = str(self.tmp / "does-not-exist.jsonl")
        result = self.run_hook(payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.records(), [])

    def test_missing_log_directory_never_fails(self) -> None:
        write_transcript(self.transcript)
        result = self.run_hook(self.payload(), log=self.tmp / "no-such-dir" / "log.jsonl")
        self.assertEqual(result.returncode, 0)
        self.assertIn("orch-telemetry", result.stderr)

    def test_record_matches_schema(self) -> None:
        try:
            jsonschema = importlib.import_module("jsonschema")
        except ImportError:
            self.skipTest("jsonschema not installed")
        write_transcript(self.transcript)
        self.run_hook(self.payload())
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(self.records()[0])


if __name__ == "__main__":
    unittest.main()
