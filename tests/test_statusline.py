import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "orchestrator" / "statusline.py"


def run(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True, timeout=10, check=False
    )


class StatuslineTests(unittest.TestCase):
    def test_full_segment(self) -> None:
        cache = {
            "warm": True,
            "hit_ratio": 0.914,
            "misses": 0,
            "expires_at": time.time() + 190,
            "caching_observed": True,
        }
        data = {"context_window": {"used_percentage": 42.4}, "prompt_cache": cache}
        self.assertEqual(run(json.dumps(data)).stdout, "ctx 42% · cache: hit 91% 3m\n")

    def test_cold_miss_and_unknown_ratio(self) -> None:
        self.assertEqual(run(json.dumps({"prompt_cache": {"warm": False}})).stdout, "cache: frío\n")
        warm = {"warm": True, "hit_ratio": None, "misses": 3, "expires_at": None}
        self.assertEqual(run(json.dumps({"prompt_cache": warm})).stdout, "cache: caliente miss 3\n")

    def test_missing_fields_omit_segments(self) -> None:
        self.assertEqual(run(json.dumps({"context_window": {"used_percentage": 7}})).stdout, "ctx 7%\n")
        self.assertEqual(run(json.dumps({"context_window": {"used_percentage": None}})).stdout, "\n")
        self.assertEqual(run("{}").stdout, "\n")
        self.assertEqual(run(json.dumps({"context_window": "x", "prompt_cache": []})).stdout, "\n")
        self.assertEqual(run(json.dumps({"prompt_cache": {"warm": True, "caching_observed": False}})).stdout, "\n")

    def test_empty_or_invalid_input(self) -> None:
        for stdin in ("", "not json", "[1]"):
            result = run(stdin)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, ""), stdin)

    def test_wrap_keeps_output_and_appends(self) -> None:
        data = json.dumps({"context_window": {"used_percentage": 10}})
        code = "import sys; print('mine ' + str(len(sys.stdin.read()) > 0))"
        result = run(data, "--wrap", f'{sys.executable} -c "{code}"')
        self.assertEqual(result.stdout, "mine True ctx 10%\n")

    def test_wrap_failures_are_ignored(self) -> None:
        data = json.dumps({"context_window": {"used_percentage": 10}})
        self.assertEqual(run(data, "--wrap", "/nonexistent/cmd").stdout, "ctx 10%\n")
        self.assertEqual(run(data, "--wrap", "'unbalanced").stdout, "ctx 10%\n")

    def test_wrap_does_not_use_a_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "m"
            run("{}", "--wrap", f"echo hi ; touch {marker}")
            self.assertFalse(marker.exists())

    def test_wrap_timeout(self) -> None:
        result = run(json.dumps({"context_window": {"used_percentage": 1}}), "--wrap", "sleep 5")
        self.assertEqual((result.returncode, result.stdout), (0, "ctx 1%\n"))


if __name__ == "__main__":
    unittest.main()
