"""Tests for orchestrator/doctor.py: every check against a real temporary installation.

Each test installs relevo into a temporary prefix, breaks one thing and runs the installed doctor. Nothing here
touches the real ~/.claude.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "relevo_install.py"
DOCTOR = ROOT / "orchestrator" / "doctor.py"


def load_doctor() -> Any:
    spec = importlib.util.spec_from_file_location("relevo_doctor", DOCTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["relevo_doctor"] = module
    spec.loader.exec_module(module)
    return module


doctor = load_doctor()


def snapshot(*bases: Path) -> dict[str, tuple[bytes, int]]:
    out: dict[str, tuple[bytes, int]] = {}
    for base in bases:
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                path = Path(dirpath) / name
                out[str(path)] = (path.read_bytes(), stat.S_IMODE(path.lstat().st_mode))
    return out


class DoctorCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.home = tmp / "home"
        self.home.mkdir()
        self.prefix = tmp / "prefix"
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "install", "--prefix", str(self.prefix)],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.project = tmp / "project"
        (self.project / ".git").mkdir(parents=True)
        (self.project / ".gitignore").write_text(".claude/work/\n", encoding="utf-8")

    def env(self) -> dict[str, str]:
        # Without the bytecode switches of the Makefile: a doctor that imported a module would write __pycache__.
        skip = ("ORCH_LOG", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX")
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k not in skip}
        env["HOME"] = str(self.home)
        return env

    def run_doctor(self, *extra: str) -> tuple[int, dict[str, dict[str, Any]], str]:
        result = subprocess.run(
            [
                sys.executable,
                str(self.prefix / "orchestrator" / "doctor.py"),
                "--json",
                "--project",
                str(self.project),
                *extra,
            ],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        data = json.loads(result.stdout)
        return result.returncode, {check["id"]: check for check in data["checks"]}, result.stderr

    def status(self, check_id: str) -> str:
        checks = self.run_doctor()[1]
        status: str = checks[check_id]["status"]
        return status

    def settings(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self.prefix / "settings.json").read_text(encoding="utf-8"))
        return data

    def write_settings(self, data: dict[str, Any]) -> None:
        (self.prefix / "settings.json").write_text(json.dumps(data), encoding="utf-8")


class CleanInstallTests(DoctorCase):
    def test_fresh_install_passes_every_check(self) -> None:
        code, checks, stderr = self.run_doctor()
        self.assertEqual(code, 0, stderr)
        self.assertEqual(list(checks), list(doctor.CHECK_IDS))
        self.assertEqual({c["status"] for c in checks.values()}, {"pass"}, checks)

    def test_doctor_is_read_only(self) -> None:
        (self.prefix / "hooks" / "orch-resume").chmod(0o644)  # a failing check must not be fixed either
        before = snapshot(self.prefix, self.project)
        code, _checks, _ = self.run_doctor()
        subprocess.run(
            [sys.executable, str(self.prefix / "orchestrator" / "doctor.py"), "--project", str(self.project)],
            env=self.env(),
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(code, 1)
        self.assertEqual(snapshot(self.prefix, self.project), before)
        self.assertFalse(list(self.prefix.rglob("__pycache__")))

    def test_default_prefix_is_the_installation_that_holds_the_script(self) -> None:
        result = subprocess.run(
            [sys.executable, str(self.prefix / "orchestrator" / "doctor.py"), "--json"],
            cwd=self.project,
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(os.path.realpath(json.loads(result.stdout)["prefix"]), os.path.realpath(self.prefix))

    def test_text_output_lists_ids_and_remedies(self) -> None:
        (self.project / ".gitignore").unlink()
        result = subprocess.run(
            [sys.executable, str(self.prefix / "orchestrator" / "doctor.py"), "--project", str(self.project)],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0)  # a warning is not a failure
        for check_id in doctor.CHECK_IDS:
            self.assertIn(check_id, result.stdout)
        self.assertRegex(result.stdout, r"(?m)^warn\s+gitignore:work")
        self.assertIn("remedio: ejecuta /orchestrator-init", result.stdout)
        self.assertIn("No se ha cambiado nada.", result.stdout)


class BrokenInstallTests(DoctorCase):
    def assert_fails(self, check_id: str) -> dict[str, Any]:
        code, checks, _ = self.run_doctor()
        self.assertEqual(checks[check_id]["status"], "fail", checks[check_id])
        self.assertEqual(code, 1)
        self.assertTrue(checks[check_id]["remedy"])
        return dict(checks[check_id])

    def test_invalid_agent_frontmatter(self) -> None:
        path = self.prefix / "agents" / "rapido.md"
        path.write_text(path.read_text(encoding="utf-8").replace("model: haiku", "model: gpt"), encoding="utf-8")
        result = self.assert_fails("frontmatter:valid")
        self.assertTrue(any("rapido.md" in d and "model" in d for d in result["details"]), result)

    def test_agent_without_frontmatter_or_max_turns(self) -> None:
        (self.prefix / "agents" / "verificador.md").write_text("sin frontmatter\n", encoding="utf-8")
        path = self.prefix / "agents" / "rapido.md"
        path.write_text(path.read_text(encoding="utf-8").replace("maxTurns: 15\n", ""), encoding="utf-8")
        details = "\n".join(self.assert_fails("frontmatter:valid")["details"])
        self.assertIn("verificador.md: no empieza por '---'", details)
        self.assertIn("rapido.md: maxTurns", details)

    def test_project_agent_with_a_worker_name_is_a_warning(self) -> None:
        (self.project / ".claude" / "agents").mkdir(parents=True)
        (self.project / ".claude" / "agents" / "implementador.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        self.assertEqual(self.status("frontmatter:valid"), "warn")

    def test_hook_not_executable_missing_or_world_writable(self) -> None:
        (self.prefix / "hooks" / "orch-resume").chmod(0o644)
        (self.prefix / "hooks" / "guard-secrets").unlink()
        (self.prefix / "hooks" / "block-force-push").chmod(0o757)
        details = "\n".join(self.assert_fails("hooks:executable")["details"])
        self.assertIn("orch-resume: no es ejecutable", details)
        self.assertIn("guard-secrets: no existe", details)
        self.assertIn("block-force-push: cualquier usuario", details)

    def test_orch_resume_must_be_registered_for_compact_and_resume(self) -> None:
        settings = self.settings()
        settings["hooks"]["SessionStart"] = [g for g in settings["hooks"]["SessionStart"] if g["matcher"] != "resume"]
        self.write_settings(settings)
        self.assertEqual(self.assert_fails("hooks:registered")["details"], ["SessionStart (resume) → orch-resume"])

    def test_one_group_matching_compact_or_resume_is_enough(self) -> None:
        settings = self.settings()
        command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        settings["hooks"]["SessionStart"] = [
            {"matcher": "compact|resume", "hooks": [{"type": "command", "command": command}]}
        ]
        self.write_settings(settings)
        self.assertEqual(self.status("hooks:registered"), "pass")

    def test_guard_secrets_matcher_must_cover_read(self) -> None:
        settings = self.settings()
        for group in settings["hooks"]["PreToolUse"]:
            if group["matcher"] == "Bash|Grep|Read":
                group["matcher"] = "Bash|Grep"
        self.write_settings(settings)
        self.assertEqual(self.assert_fails("hooks:registered")["details"], ["PreToolUse (Read) → guard-secrets"])

    def test_hook_registered_for_another_path_does_not_count(self) -> None:
        settings = self.settings()
        settings["hooks"]["SubagentStop"][0]["hooks"][0]["command"] = "/elsewhere/orch-telemetry"
        self.write_settings(settings)
        self.assertEqual(self.assert_fails("hooks:registered")["details"], ["SubagentStop → orch-telemetry"])

    def test_disable_all_hooks_in_the_project_fails(self) -> None:
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "settings.local.json").write_text('{"disableAllHooks": true}', encoding="utf-8")
        details = self.assert_fails("hooks:registered")["details"]
        self.assertTrue(any("disableAllHooks" in d and "settings.local.json" in d for d in details), details)

    def test_settings_with_comments_fail_instead_of_crashing(self) -> None:
        (self.prefix / "settings.json").write_text("{\n  // comment\n}\n", encoding="utf-8")
        self.assert_fails("hooks:registered")
        self.assert_fails("env")

    def test_spawn_depth_other_than_one_fails(self) -> None:
        settings = self.settings()
        settings["env"]["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] = "2"
        del settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"]
        self.write_settings(settings)
        details = "\n".join(self.assert_fails("env")["details"])
        self.assertIn("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH es '2'", details)
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL", details)

    def test_missing_subagent_model_is_only_a_warning(self) -> None:
        settings = self.settings()
        del settings["env"]["CLAUDE_CODE_SUBAGENT_MODEL"]
        self.write_settings(settings)
        self.assertEqual(self.status("env"), "warn")

    def test_modified_file_is_a_warning_and_missing_file_a_failure(self) -> None:
        with open(self.prefix / "agents" / "rapido.md", "a", encoding="utf-8") as handle:
            handle.write("\nlocal\n")
        _code, checks, _ = self.run_doctor()
        self.assertEqual(checks["manifest:drift"]["status"], "warn")
        self.assertIn("modificado desde la instalación: agents/rapido.md", checks["manifest:drift"]["details"])
        (self.prefix / "orchestrator" / "stats.py").unlink()
        self.assertIn("falta orchestrator/stats.py", self.assert_fails("manifest:drift")["details"])

    def test_removed_force_push_deny_rule_fails(self) -> None:
        settings = self.settings()
        settings["permissions"]["deny"] = []
        self.write_settings(settings)
        details = self.assert_fails("manifest:drift")["details"]
        self.assertIn("permissions.deny ya no contiene 'Bash(git push --force:*)'", details)

    def test_no_manifest_is_a_warning(self) -> None:
        (self.prefix / "orchestrator" / ".relevo-manifest.json").unlink()
        _code, checks, _ = self.run_doctor()
        self.assertEqual(checks["manifest:drift"]["status"], "warn")

    def test_claude_md_without_the_policy_import_fails(self) -> None:
        (self.prefix / "CLAUDE.md").write_text("# mío\n", encoding="utf-8")
        self.assert_fails("claude-md:import")

    def test_project_config_not_imported_is_a_warning(self) -> None:
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "orchestrator.md").write_text("# proyecto\n", encoding="utf-8")
        self.assertEqual(self.status("claude-md:import"), "warn")
        (self.project / "CLAUDE.md").write_text("@.claude/orchestrator.md\n", encoding="utf-8")
        self.assertEqual(self.status("claude-md:import"), "pass")

    def test_work_dir_not_ignored_is_a_warning(self) -> None:
        (self.project / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        self.assertEqual(self.status("gitignore:work"), "warn")

    def test_project_outside_git_does_not_apply(self) -> None:
        (self.project / ".git").rmdir()
        if doctor.git_root(self.project) is None:  # the temporary directory may live inside a repository
            self.assertEqual(self.status("gitignore:work"), "pass")

    def test_hand_edited_table_b_fails(self) -> None:
        policy = self.prefix / "orchestrator" / "policy.md"
        text = policy.read_text(encoding="utf-8")
        policy.write_text(text.replace("≤2 archivos", "≤9 archivos", 1), encoding="utf-8")
        self.assertNotEqual(policy.read_text(encoding="utf-8"), text)
        self.assertEqual(self.assert_fails("routing:sync")["details"], ["orchestrator/policy.md"])

    def test_install_without_routing_json_is_a_warning(self) -> None:
        (self.prefix / "orchestrator" / "routing.json").unlink()
        _code, checks, _ = self.run_doctor()
        self.assertEqual(checks["routing:sync"]["status"], "warn")

    def test_internal_error_in_one_check_does_not_hide_the_others(self) -> None:
        ctx = doctor.Context(self.prefix, self.project, None, DOCTOR.parent)
        original = doctor.CHECKS

        def boom(_ctx: Any) -> Any:
            raise RuntimeError("boom")

        try:
            doctor.CHECKS = (boom, *original[1:])
            results = doctor.run_checks(ctx)
        finally:
            doctor.CHECKS = original
        self.assertEqual(results[0].id, "python:version")
        self.assertEqual(results[0].status, "fail")
        self.assertEqual(len(results), len(doctor.CHECK_IDS))


class DoctorConsistencyTests(unittest.TestCase):
    def test_check_ids_are_stable_and_unique(self) -> None:
        self.assertEqual(
            doctor.CHECK_IDS,
            (
                "python:version",
                "frontmatter:valid",
                "hooks:executable",
                "hooks:registered",
                "env",
                "manifest:drift",
                "claude-md:import",
                "gitignore:work",
                "routing:sync",
            ),
        )
        self.assertEqual(len(doctor.CHECKS), len(doctor.CHECK_IDS))

    def test_shipped_names_match_the_repository(self) -> None:
        self.assertEqual(sorted(doctor.AGENTS), sorted(p.stem for p in (ROOT / "agents").glob("*.md")))
        self.assertEqual(sorted(doctor.COMMANDS), sorted(p.stem for p in (ROOT / "commands").glob("*.md")))
        self.assertEqual(sorted(doctor.HOOKS), sorted(p.name for p in (ROOT / "hooks").iterdir() if p.is_file()))

    def test_expected_hooks_match_the_settings_template(self) -> None:
        template = json.loads((ROOT / "templates" / "settings.example.json").read_text(encoding="utf-8"))
        registered = set()
        for event, groups in template["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    name = hook["command"].rsplit("/", 1)[-1]
                    registered.add((event, group.get("matcher"), name))
        expected = set()
        for event, values, name in doctor.EXPECTED_HOOKS:
            matchers = {m for (e, m, n) in registered if e == event and n == name}
            self.assertTrue(matchers, (event, name))
            for value in values:
                self.assertTrue(any(doctor.matcher_covers(m, value) for m in matchers), (event, value, name))
            expected |= {(event, m, name) for m in matchers}
        self.assertEqual(expected, registered)

    def test_env_matches_the_settings_template(self) -> None:
        template = json.loads((ROOT / "templates" / "settings.example.json").read_text(encoding="utf-8"))
        self.assertEqual({**doctor.ENV_REQUIRED, **doctor.ENV_RECOMMENDED}, template["env"])

    def test_ignored_pattern_matches_orch_resume(self) -> None:
        hook = (ROOT / "hooks" / "orch-resume").read_text(encoding="utf-8")
        match = re.search(r'^IGNORED = re\.compile\((r".*")\)$', hook, re.M)
        assert match is not None
        self.assertEqual(ast.literal_eval(match.group(1)), doctor.IGNORED.pattern)

    def test_parse_frontmatter(self) -> None:
        fields, errors = doctor.parse_frontmatter('---\nname: "x"\nname: y\nmal\n---\nbody\n')
        self.assertEqual(fields["name"], "y")
        self.assertEqual(errors, ["clave repetida 'name'", "línea 4 no es 'clave: valor'"])
        self.assertEqual(doctor.parse_frontmatter("---\nname: x\n")[1], ["falta el '---' de cierre"])

    def test_matcher_covers(self) -> None:
        self.assertTrue(doctor.matcher_covers("Bash|Grep|Read", "Read"))
        self.assertTrue(doctor.matcher_covers(None, "Read"))
        self.assertTrue(doctor.matcher_covers("*", "Read"))
        self.assertTrue(doctor.matcher_covers(".*", "Read"))
        self.assertFalse(doctor.matcher_covers("Bash", "Read"))
        self.assertFalse(doctor.matcher_covers("Readme", "Read"))
        self.assertFalse(doctor.matcher_covers("compact", "resume"))

    def test_command_documents_that_remedies_are_not_applied(self) -> None:
        text = (ROOT / "commands" / "orch-doctor.md").read_text(encoding="utf-8")
        self.assertIn("python3 ~/.claude/orchestrator/doctor.py $ARGUMENTS", text)
        self.assertIn("No ejecutes ningún remedio", text)


if __name__ == "__main__":
    unittest.main()
