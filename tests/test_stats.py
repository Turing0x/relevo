"""Black-box tests for orchestrator/stats.py (summary of the telemetry log)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / "orchestrator" / "stats.py"

NO_DATA = "Sin datos: log.jsonl no existe todavía."
EM_DASH = chr(0x2014)  # spelled out to keep the source free of look-alike punctuation
HEADER = "Últimos {days} días " + EM_DASH + " {n} llamadas"


class StatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.log = self.home / "log.jsonl"

    def run_stats(self, *args: str) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
        env["HOME"] = str(self.home)
        env["ORCH_LOG"] = str(self.log)
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(STATS), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write_log(self, rows: list[Any]) -> None:
        with open(self.log, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write((row if isinstance(row, str) else json.dumps(row)) + "\n")

    @staticmethod
    def record(agent: str = "rapido", days_ago: float = 1, **fields: Any) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "ts": (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds"),
            "agent_id": f"{agent}-{days_ago}-{fields.get('turns', 0)}",
            "agent": agent,
            "model": "claude-haiku-5-5",
            "turns": 4,
            "in": 100,
            "cache_read": 1000,
            "cache_write": 50,
            "out_est": 200,
            "dur_s": 20,
            "status": "OK",
        }
        rec.update(fields)
        return rec

    def agent_file(self, base: Path, name: str, max_turns: int) -> None:
        folder = base / ".claude" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.md").write_text(f"---\nname: {name}\nmaxTurns: {max_turns}\n---\nbody\n", encoding="utf-8")

    def row(self, output: str, agent: str) -> list[str]:
        for line in output.splitlines():
            if line.startswith(agent):
                return line.split()
        self.fail(f"no row for {agent} in:\n{output}")

    def test_header_and_counts(self) -> None:
        self.write_log([self.record(turns=2), self.record(turns=3), self.record("verificador", turns=5)])
        output = self.run_stats()
        self.assertIn(HEADER.format(days=30, n=3), output)
        self.assertEqual(self.row(output, "rapido")[1], "2")
        self.assertEqual(self.row(output, "verificador")[1], "1")

    def test_dedupe_by_agent_id_keeps_last(self) -> None:
        first = self.record(agent_id="same", status="OK", turns=5)
        second = self.record(agent_id="same", status="RECHAZADO", turns=9)
        self.write_log([first, second])
        output = self.run_stats()
        self.assertIn(HEADER.format(days=30, n=1), output)
        self.assertIn("RECHAZADO:1", output)
        self.assertNotIn("OK:1", output)

    def test_days_filter(self) -> None:
        self.write_log([self.record(days_ago=1, turns=1), self.record(days_ago=40, turns=2)])
        self.assertIn(HEADER.format(days=30, n=1), self.run_stats())
        self.assertIn(HEADER.format(days=60, n=2), self.run_stats("60"))

    def test_corrupt_lines_are_skipped(self) -> None:
        self.write_log(["not json", self.record(turns=1), "{broken", '{"agent": 5}', "[]"])
        self.assertIn(HEADER.format(days=30, n=1), self.run_stats())

    def test_max_turns_from_global_agent(self) -> None:
        self.agent_file(self.home, "rapido", 15)
        self.write_log([self.record(turns=15), self.record(turns=3)])
        row = self.row(self.run_stats(), "rapido")
        self.assertEqual(row[4], "1")  # one call reached the cap of 15

    def test_project_agent_overrides_global(self) -> None:
        project = self.home / "project"
        self.agent_file(self.home, "rapido", 15)
        self.agent_file(project, "rapido", 3)
        self.write_log([self.record(turns=5, cwd=str(project))])
        self.assertEqual(self.row(self.run_stats(), "rapido")[4], "1")
        self.write_log([self.record(turns=5, cwd=str(self.home / "elsewhere"))])
        self.assertEqual(self.row(self.run_stats(), "rapido")[4], "0")

    def test_missing_log(self) -> None:
        self.assertIn(NO_DATA, self.run_stats())

    def test_empty_log(self) -> None:
        self.write_log([])
        self.assertIn("Sin llamadas en 30 días.", self.run_stats())

    def test_invalid_days_argument_defaults_to_30(self) -> None:
        self.write_log([self.record(turns=1)])
        for arg in ("abc", "99999999999"):
            with self.subTest(arg=arg):
                self.assertIn(HEADER.format(days=30, n=1), self.run_stats(arg))

    def test_duration_is_the_median(self) -> None:
        self.write_log([self.record(turns=n, dur_s=d) for n, d in ((1, 20), (2, 20), (3, 37754))])
        self.assertEqual(self.row(self.run_stats(), "rapido")[7], "20")

    def test_duration_median_of_even_count_and_of_nothing(self) -> None:
        self.write_log([self.record(turns=1, dur_s=10), self.record(turns=2, dur_s=20)])
        self.assertEqual(self.row(self.run_stats(), "rapido")[7], "15")
        self.write_log([self.record(turns=1, dur_s=None), self.record(turns=2, dur_s="x")])
        self.assertEqual(self.row(self.run_stats(), "rapido")[7], "0")

    def test_header_names_the_median_column(self) -> None:
        self.write_log([self.record()])
        self.assertIn("seg.med", self.run_stats())

    def test_level_block_counts_levels_rejections_and_reasons(self) -> None:
        self.write_log(
            [
                self.record("verificador", turns=1, nivel="1", motivo="tamano", status="APROBADO", dur_s=100),
                self.record("verificador", turns=2, nivel="1", motivo="tamano", status="RECHAZADO", dur_s=200),
                self.record("verificador", turns=3, nivel="2", motivo="riesgo-3", status="APROBADO"),
                self.record("verificador", turns=4, status="APROBADO"),
            ]
        )
        output = self.run_stats()
        self.assertIn("Por nivel (verificador", output)
        level_1 = next(x for x in output.splitlines() if x.startswith("  1 "))
        self.assertIn("n=2", level_1)
        self.assertIn("seg.med=150", level_1)
        self.assertIn("RECHAZADO:1", level_1)
        self.assertIn("tamano:2", level_1)
        self.assertIn("riesgo-3:1", next(x for x in output.splitlines() if x.startswith("  2 ")))
        self.assertIn("n=1", next(x for x in output.splitlines() if x.startswith("  ? ")))

    def test_no_level_block_without_levels(self) -> None:
        self.write_log([self.record("verificador", turns=1), self.record(turns=2, nivel="1")])
        self.assertNotIn("Por nivel", self.run_stats())

    def test_non_string_level_does_not_break(self) -> None:
        self.write_log(
            [
                self.record("verificador", turns=1, nivel="1", motivo=["x"]),
                self.record("verificador", turns=2, nivel=7, motivo={"a": 1}),
            ]
        )
        output = self.run_stats()
        self.assertIn("Por nivel", output)
        self.assertIn("n=1", next(x for x in output.splitlines() if x.startswith("  ? ")))

    def test_cost_per_record_and_total(self) -> None:
        opus = self.record("arquitecto", turns=1, model="claude-opus-5-5", cache_write=1000)
        sonnet = self.record("implementador", turns=1, model="claude-sonnet-5-5", cache_write=1000)
        self.write_log([opus, sonnet])
        output = self.run_stats()
        # opus: 100*4 + 1000*4*2 + 1000*0.2 + 200*20 = 12600 -> $0.0126 ; sonnet: half
        self.assertEqual(self.row(output, "arquitecto")[8], "0.01")
        self.assertIn("Total estimado: $0.02", output)
        self.assertNotIn("sin precio", output)

    def test_unknown_model_is_counted_not_priced(self) -> None:
        self.write_log([self.record(turns=1, model="claude-x"), self.record(turns=2, model=None)])
        output = self.run_stats()
        self.assertIn("Total estimado: $0.00", output)
        self.assertIn("2 registros sin precio", output)

    def test_total_is_sum_of_records(self) -> None:
        big: dict[str, Any] = {"in": 1_000_000, "cache_read": 0, "cache_write": 0, "out_est": 0}
        self.write_log(
            [
                self.record(turns=1, model="claude-opus-5-5", **big),
                self.record("x", turns=2, model="claude-sonnet-5-5", **big),
            ]
        )
        self.assertIn("Total estimado: $6.00", self.run_stats())

    def test_level_by_model_with_escalated(self) -> None:
        self.write_log(
            [
                self.record("verificador", turns=1, nivel="1", model="claude-sonnet-5-5", status="RECHAZADO"),
                self.record("verificador", turns=2, nivel="1", model="claude-sonnet-5-5", motivo="escalado"),
                self.record("verificador", turns=3, nivel="1", model="claude-opus-5-5", status="APROBADO"),
            ]
        )
        lines = self.run_stats().splitlines()
        sonnet = next(x for x in lines if x.startswith("  1 ") and "sonnet-5-5" in x)
        self.assertIn("n=2", sonnet)
        self.assertIn("RECHAZADO:1 (50%)", sonnet)
        self.assertIn("escalado:1", sonnet)
        opus = next(x for x in lines if x.startswith("  1 ") and "opus-5-5" in x)
        self.assertIn("escalado:0", opus)


if __name__ == "__main__":
    unittest.main()
