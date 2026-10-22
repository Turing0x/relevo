"""Static checks for .github/workflows, dependabot.yml and scripts/setup-github.sh.

Uses PyYAML when it is installed; otherwise falls back to regular expressions
for the checks that can be expressed that way.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the environment
    yaml = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SETUP = ROOT / "scripts" / "setup-github.sh"

EXPECTED_FILES = {
    "ci.yml",
    "docs.yml",
    "secret-scan.yml",
    "codeql.yml",
    "dependency-review.yml",
    "dco.yml",
    "sensitive-paths.yml",
}
EXPECTED_REQUIRED = ["ci-ok", "docs-check", "gitleaks", "dco", "dependency-review"]
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)\s*(#.*)?$")
PINNED_RE = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT_RE = re.compile(r"^#\s*v\d+\.\d+\.\d+\s*$")


def strip_comments(text: str) -> str:
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())


def triggers(data: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML (YAML 1.1) parses the bare key `on` as the boolean True.
    raw = data.get("on", data.get(True))
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {name: None for name in raw}
    return dict(raw or {})


def load(path: Path) -> dict[Any, Any]:
    assert yaml is not None
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def regex_jobs(text: str) -> dict[str, str]:
    """Fallback: split the `jobs:` mapping into {job id: block text}."""
    body = re.split(r"^jobs:\s*$", text, maxsplit=1, flags=re.MULTILINE)[1]
    parts = re.split(r"^  ([\w-]+):\s*$", body, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class WorkflowFilesTest(unittest.TestCase):
    def test_expected_workflow_set(self) -> None:
        self.assertEqual({p.name for p in WORKFLOWS}, EXPECTED_FILES)

    def test_external_actions_are_pinned_by_sha_with_version_comment(self) -> None:
        for path in WORKFLOWS:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = USES_RE.match(line)
                if not match or match.group(1).startswith("./"):
                    continue
                with self.subTest(file=path.name, line=number):
                    self.assertRegex(match.group(1), PINNED_RE)
                    self.assertIsNotNone(match.group(2), "missing '# vX.Y.Z' comment")
                    self.assertRegex(match.group(2), VERSION_COMMENT_RE)

    def test_top_level_permissions_and_job_timeouts(self) -> None:
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertRegex(text, re.compile(r"^permissions:", re.MULTILINE))
                self.assertRegex(text, re.compile(r"^permissions:\s*\n\s+contents: read\s*$", re.MULTILINE))
                jobs = regex_jobs(text)
                self.assertTrue(jobs)
                for job_id, block in jobs.items():
                    self.assertRegex(block, r"(?m)^    timeout-minutes:\s*\d+\s*$", job_id)

    def test_every_checkout_does_not_persist_credentials(self) -> None:
        for path in WORKFLOWS:
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                match = USES_RE.match(line)
                if not match or not match.group(1).startswith("actions/checkout@"):
                    continue
                step: list[str] = []
                for follower in lines[index + 1 :]:
                    if re.match(r"^\s*- ", follower) or (follower.strip() and not follower.startswith(" ")):
                        break
                    step.append(follower)
                with self.subTest(file=path.name, line=index + 1):
                    self.assertTrue(
                        any(re.match(r"^\s+persist-credentials:\s*false\s*$", s) for s in step),
                        "checkout without persist-credentials: false",
                    )

    def test_no_secrets_anywhere(self) -> None:
        for path in WORKFLOWS:
            with self.subTest(file=path.name):
                self.assertNotIn("secrets.", strip_comments(path.read_text(encoding="utf-8")))

    def test_no_path_filters(self) -> None:
        # A required check behind a paths filter would stay pending forever.
        for path in WORKFLOWS:
            with self.subTest(file=path.name):
                self.assertNotRegex(strip_comments(path.read_text(encoding="utf-8")), r"(?m)^\s+paths(-ignore)?:")

    def test_run_blocks_never_interpolate_expressions(self) -> None:
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                if yaml is None:
                    self.assertNotRegex(strip_comments(text), r"(?m)^\s*(?:-\s+)?run:.*\$\{\{")
                    continue
                for job_id, job in load(path)["jobs"].items():
                    for step in job.get("steps", []):
                        if "run" in step:
                            self.assertNotIn("${{", step["run"], f"{job_id}: {step.get('name')}")

    def test_no_model_api_calls_or_fork_secret_paths(self) -> None:
        for path in WORKFLOWS:
            text = strip_comments(path.read_text(encoding="utf-8")).lower()
            with self.subTest(file=path.name):
                for needle in ("anthropic", "openai", "api_key", "claude-code-action"):
                    self.assertNotIn(needle, text)

    def test_pull_request_target_never_checks_out_pr_code(self) -> None:
        found = False
        for path in WORKFLOWS:
            text = strip_comments(path.read_text(encoding="utf-8"))
            if "pull_request_target" not in text:
                continue
            found = True
            with self.subTest(file=path.name):
                self.assertEqual(path.name, "sensitive-paths.yml")
                for ref in re.findall(r"(?m)^\s+ref:\s*(.+)$", text):
                    self.assertNotIn("head", ref.lower())
                    self.assertNotIn("refs/pull", ref)
                    self.assertIn("pull_request.base.sha", ref)
                self.assertIn("persist-credentials: false", text)
                self.assertIn("sparse-checkout: scripts/sensitive_diff.py", text)
        self.assertTrue(found, "sensitive-paths.yml should use pull_request_target")

    def test_pull_request_target_is_not_used_elsewhere(self) -> None:
        for path in WORKFLOWS:
            if path.name != "sensitive-paths.yml":
                self.assertNotIn("pull_request_target", strip_comments(path.read_text(encoding="utf-8")), path.name)
                self.assertNotIn("workflow_run", strip_comments(path.read_text(encoding="utf-8")), path.name)

    def test_sensitive_paths_permissions_are_minimal(self) -> None:
        text = (ROOT / ".github" / "workflows" / "sensitive-paths.yml").read_text(encoding="utf-8")
        block = strip_comments(regex_jobs(text)["label"])
        self.assertRegex(block, r"(?m)^      contents: read$")
        self.assertRegex(block, r"(?m)^      pull-requests: write$")
        write_lines = re.findall(r"(?m)^\s+[\w-]+: write$", strip_comments(text))
        self.assertEqual([ln.strip() for ln in write_lines], ["pull-requests: write"])

    def test_codeql_has_only_the_needed_write_permission(self) -> None:
        text = strip_comments((ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8"))
        write_lines = re.findall(r"(?m)^\s+[\w-]+: write$", text)
        self.assertEqual([ln.strip() for ln in write_lines], ["security-events: write"])
        self.assertIn("github.event.repository.private != true", text)

    def test_other_workflows_have_no_write_permissions(self) -> None:
        for path in WORKFLOWS:
            if path.name in ("codeql.yml", "sensitive-paths.yml"):
                continue
            with self.subTest(file=path.name):
                self.assertNotRegex(strip_comments(path.read_text(encoding="utf-8")), r"(?m): write$")

    def test_ci_ok_aggregates_every_other_job(self) -> None:
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        jobs = regex_jobs(text)
        needs = re.search(r"(?m)^    needs:\s*\[(.*?)\]\s*$", jobs["ci-ok"])
        self.assertIsNotNone(needs)
        assert needs is not None
        listed = {n.strip() for n in needs.group(1).split(",")}
        self.assertEqual(listed, set(jobs) - {"ci-ok"})
        self.assertRegex(jobs["ci-ok"], r"(?m)^    if: always\(\)\s*$")
        self.assertRegex(jobs["ci-ok"], r"(?m)^    permissions: \{\}\s*$")
        self.assertIn("join(needs.*.result", jobs["ci-ok"])

    def test_ci_calls_make_targets_and_macos_uses_system_python(self) -> None:
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for target in ("make lint", "make lint-workflows", "make typecheck", "make test"):
            self.assertIn(target, text)
        self.assertIn("make test PY=/usr/bin/python3", text)
        self.assertIn('ACTIONLINT="$RUNNER_TEMP/actionlint"', text)
        self.assertIn("macos-15", text)
        self.assertIn("ubuntu-24.04", text)

    def test_downloaded_binaries_are_checksum_verified(self) -> None:
        # Release-asset checksums (public, not credentials). Kept apart from the workflow file names: a hex
        # string next to "secret-scan.yml" trips the generic-api-key rule of gitleaks.
        digests = {
            "actionlint": "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
            "gitleaks": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
        }
        workflow_of = {"actionlint": "ci.yml", "gitleaks": "secret-scan.yml"}
        for tool, digest in digests.items():
            name = workflow_of[tool]
            text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            with self.subTest(file=name):
                self.assertIn(digest, text)
                self.assertIn("sha256sum -c", text)

    @unittest.skipIf(yaml is None, "PyYAML not installed")
    def test_job_names_match_ids_and_yaml_parses(self) -> None:
        for path in WORKFLOWS:
            data = load(path)
            self.assertIn("name", data)
            self.assertIsNotNone(data["jobs"])
            for job_id, job in data["jobs"].items():
                name = job.get("name", job_id)
                with self.subTest(file=path.name, job=job_id):
                    if "${{" in name:  # matrix legs keep the id as display prefix
                        self.assertTrue(name.startswith(job_id), name)
                    else:
                        self.assertEqual(name, job_id)

    @unittest.skipIf(yaml is None, "PyYAML not installed")
    def test_workflow_names_and_triggers(self) -> None:
        expected = {
            "ci.yml": ("CI", {"push", "pull_request", "workflow_dispatch"}),
            "docs.yml": ("Docs", {"push", "pull_request", "schedule", "workflow_dispatch"}),
            "secret-scan.yml": ("Secret scan", {"push", "pull_request"}),
            "dco.yml": ("DCO", {"pull_request"}),
            "dependency-review.yml": ("Dependency review", {"pull_request"}),
            "codeql.yml": ("CodeQL", {"push", "pull_request", "schedule"}),
            "sensitive-paths.yml": ("Sensitive paths", {"pull_request_target"}),
        }
        for name, (title, events) in expected.items():
            data = load(ROOT / ".github" / "workflows" / name)
            with self.subTest(file=name):
                self.assertEqual(data["name"], title)
                self.assertEqual(set(triggers(data)), events)

    @unittest.skipIf(yaml is None, "PyYAML not installed")
    def test_dependabot_config(self) -> None:
        data = load(ROOT / ".github" / "dependabot.yml")
        self.assertEqual(data["version"], 2)
        ecosystems = {u["package-ecosystem"]: u for u in data["updates"]}
        self.assertEqual(set(ecosystems), {"github-actions", "pip"})
        for update in ecosystems.values():
            self.assertEqual(update["directory"], "/")
            self.assertEqual(update["schedule"]["interval"], "weekly")
            self.assertEqual(update["labels"], ["dependencies"])
            self.assertEqual(update["open-pull-requests-limit"], 5)
            self.assertIn("groups", update)


class RequiredChecksTest(unittest.TestCase):
    def required_from_script(self) -> list[str]:
        match = re.search(r'(?m)^REQUIRED_CHECKS="([^"]*)"', SETUP.read_text(encoding="utf-8"))
        self.assertIsNotNone(match)
        assert match is not None
        return match.group(1).split()

    def test_required_checks_constant(self) -> None:
        self.assertEqual(self.required_from_script(), EXPECTED_REQUIRED)

    def test_required_checks_are_pr_jobs_without_path_filters(self) -> None:
        provided: dict[str, str] = {}
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            if not re.search(r"(?m)^  pull_request:", text) and not re.search(r"(?m)^on:.*pull_request", text):
                continue
            self.assertNotRegex(strip_comments(text), r"(?m)^\s+paths(-ignore)?:", path.name)
            for block in regex_jobs(text).values():
                name = re.search(r"(?m)^    name:\s*(.+?)\s*$", block)
                if name and "${{" not in name.group(1):
                    provided[name.group(1)] = path.name
        for check in self.required_from_script():
            with self.subTest(check=check):
                self.assertIn(check, provided)

    def test_required_check_job_ids_equal_names(self) -> None:
        owners = {
            "ci-ok": "ci.yml",
            "docs-check": "docs.yml",
            "gitleaks": "secret-scan.yml",
            "dco": "dco.yml",
            "dependency-review": "dependency-review.yml",
        }
        for check, file in owners.items():
            block = regex_jobs((ROOT / ".github" / "workflows" / file).read_text(encoding="utf-8"))[check]
            self.assertRegex(block, rf"(?m)^    name:\s*{re.escape(check)}\s*$")

    def test_labels_constant_matches_plan(self) -> None:
        text = SETUP.read_text(encoding="utf-8")
        match = re.search(r'(?ms)^LABELS="(.*?)"$', text)
        self.assertIsNotNone(match)
        assert match is not None
        names = [line.split("|")[0] for line in match.group(1).splitlines()]
        self.assertEqual(
            names,
            [
                "bug",
                "enhancement",
                "docs",
                "good first issue",
                "help wanted",
                "security-sensitive",
                "new-agent",
                "question",
                "dependencies",
            ],
        )
        for line in match.group(1).splitlines():
            self.assertRegex(line.split("|")[1], r"^[0-9a-f]{6}$")


class SetupScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.marker = self.tmp / "gh-was-called"
        stub_dir = self.tmp / "bin"
        stub_dir.mkdir()
        stub = stub_dir / "gh"
        stub.write_text(f'#!/bin/sh\necho called >> "{self.marker}"\nexit 1\n', encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.env = {
            "PATH": f"{stub_dir}:/usr/bin:/bin",
            "HOME": str(self.tmp / "home"),
            "ORCH_LOG": str(self.tmp / "log.jsonl"),
        }

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SETUP), *args], env=self.env, cwd=self.tmp, capture_output=True, text=True)

    def test_is_executable_and_valid_syntax(self) -> None:
        self.assertTrue(os.access(SETUP, os.X_OK))
        result = subprocess.run(["bash", "-n", str(SETUP)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_header_warns_against_running_without_approval(self) -> None:
        head = "\n".join(SETUP.read_text(encoding="utf-8").splitlines()[:12])
        self.assertIn("do NOT run this script without maintainer approval", head)

    def test_dry_run_never_calls_gh(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.marker.exists(), "gh was invoked during the dry run")
        self.assertIn("DRY RUN", result.stdout)
        for expected in (
            "--enable-squash-merge",
            "--enable-discussions",
            "web_commit_signoff_required=true",
            "sha_pinning_required",
            "first_time_contributors",
            "main protection",
            "gh label create",
        ):
            self.assertIn(expected, result.stdout)

    def test_dry_run_sets_no_homepage_and_no_funding(self) -> None:
        result = self.run_script()
        self.assertNotIn("homepage", result.stdout.lower())
        self.assertNotIn("--homepage", SETUP.read_text(encoding="utf-8").replace("# NOT set", ""))
        self.assertNotIn("funding", result.stdout.lower())

    def test_dry_run_json_bodies_are_valid(self) -> None:
        result = self.run_script()
        bodies = re.findall(r"<<'JSON'\n(.*?)\nJSON\n", result.stdout, flags=re.DOTALL)
        self.assertGreaterEqual(len(bodies), 5)
        parsed = [json.loads(b) for b in bodies]
        ruleset = next(p for p in parsed if p.get("name") == "main protection")
        rules = {r["type"]: r.get("parameters", {}) for r in ruleset["rules"]}
        self.assertEqual(ruleset["enforcement"], "active")
        self.assertEqual(ruleset["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"])
        for rule in (
            "deletion",
            "non_fast_forward",
            "required_linear_history",
            "pull_request",
            "required_status_checks",
        ):
            self.assertIn(rule, rules)
        pr = rules["pull_request"]
        self.assertEqual(pr["required_approving_review_count"], 1)
        self.assertTrue(pr["require_code_owner_review"])
        self.assertTrue(pr["required_review_thread_resolution"])
        self.assertEqual(pr["allowed_merge_methods"], ["squash"])
        checks = rules["required_status_checks"]["required_status_checks"]
        self.assertEqual([c["context"] for c in checks], EXPECTED_REQUIRED)
        self.assertEqual({c["integration_id"] for c in checks}, {15368})

    def test_repo_override_via_environment(self) -> None:
        self.env["REPO"] = "someone/else"
        result = self.run_script()
        self.assertIn("someone/else", result.stdout)
        self.assertNotIn("Turing0x/relevo", result.stdout)

    def test_help_and_bad_argument(self) -> None:
        helped = self.run_script("--help")
        self.assertEqual(helped.returncode, 0)
        self.assertIn("--apply", helped.stdout)
        bad = self.run_script("--nope")
        self.assertEqual(bad.returncode, 2)
        self.assertFalse(self.marker.exists())

    def test_apply_without_gh_authentication_aborts_before_changes(self) -> None:
        # The stub fails every call (exit 1): `gh auth status` fails, so nothing is changed.
        result = self.run_script("--apply")
        self.assertEqual(result.returncode, 1)
        calls = self.marker.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1, "only the auth check may run")


if __name__ == "__main__":
    unittest.main()
