"""Tests for scripts/relevo_install.py: end-to-end through the CLI and unit tests of the merge logic.

Every run uses a temporary HOME and a temporary prefix. Nothing here touches the real ~/.claude.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "relevo_install.py"
TEMPLATE = json.loads((ROOT / "templates" / "settings.example.json").read_text(encoding="utf-8"))
DEPTH = "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"


def load_installer() -> Any:
    spec = importlib.util.spec_from_file_location("relevo_install", INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["relevo_install"] = module
    spec.loader.exec_module(module)
    return module


relevo_install = load_installer()


def snapshot(base: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            path = Path(dirpath) / name
            out[path.relative_to(base).as_posix()] = path.read_bytes()
    return out


class InstallerCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.prefix = self.tmp / "prefix"

    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k != "ORCH_LOG"}
        env["HOME"] = str(self.home)
        return env

    def run_cli(self, *args: str, script: Path = INSTALLER) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            text=True,
            env=self.env(),
            timeout=120,
            check=False,
        )

    def install(self, *extra: str, script: Path = INSTALLER) -> subprocess.CompletedProcess[str]:
        return self.run_cli("install", "--prefix", str(self.prefix), *extra, script=script)

    def uninstall(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli("uninstall", "--prefix", str(self.prefix), *extra)

    def write_settings(self, data: Any) -> Path:
        self.prefix.mkdir(parents=True, exist_ok=True)
        path = self.prefix / "settings.json"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    def settings(self) -> dict[str, Any]:
        return json.loads((self.prefix / "settings.json").read_text(encoding="utf-8"))

    def backups(self) -> list[Path]:
        folder = self.prefix / ".relevo-backups"
        return sorted(folder.iterdir()) if folder.exists() else []

    def make_source_copy(self) -> Path:
        """A private copy of the repo parts the installer reads, so a test can edit the 'release'."""
        src = self.tmp / "src"
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        for name in ("agents", "hooks", "commands", "orchestrator", "docs", "templates"):
            shutil.copytree(ROOT / name, src / name, ignore=ignore)
        (src / "scripts").mkdir()
        shutil.copy2(INSTALLER, src / "scripts" / "relevo_install.py")
        return src / "scripts" / "relevo_install.py"

    USER_SETTINGS: ClassVar[dict[str, Any]] = {
        "model": "opus",
        "env": {"FOO": "bar"},
        "permissions": {"allow": ["Bash(ls:*)"], "ask": ["Bash(git push:*)", "Bash(my-tool:*)"]},
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/local/bin/mine"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "/usr/local/bin/bye"}]}],
        },
    }


class FreshInstallTests(InstallerCase):
    def test_tree_modes_and_settings(self) -> None:
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        for agent in (ROOT / "agents").glob("*.md"):
            self.assertEqual((self.prefix / "agents" / agent.name).read_bytes(), agent.read_bytes())
        for hook in (ROOT / "hooks").iterdir():
            installed = self.prefix / "hooks" / hook.name
            self.assertEqual(stat.S_IMODE(installed.stat().st_mode), 0o755, hook.name)
            self.assertEqual(installed.read_bytes(), hook.read_bytes())
        for command in (ROOT / "commands").glob("*.md"):
            self.assertTrue((self.prefix / "commands" / command.name).is_file())
        for name in ("policy.md", "project-template.md", "stats.py"):
            self.assertTrue((self.prefix / "orchestrator" / name).is_file(), name)
        self.assertEqual(
            (self.prefix / "orchestrator" / "docs" / "contracts" / "brief.schema.json").read_bytes(),
            (ROOT / "docs" / "contracts" / "brief.schema.json").read_bytes(),
        )
        for absent in ("templates", "scripts", "tests", ".github", "docs"):
            self.assertFalse((self.prefix / absent).exists(), absent)
        manifest = json.loads((self.prefix / "orchestrator" / ".relevo-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], relevo_install.VERSION)
        self.assertIn("agents/rapido.md", manifest["files"])
        self.assertTrue(manifest["claude_md_block"])
        # Paths of a non-default prefix are rewritten to the prefix.
        template_text = (ROOT / "templates" / "settings.example.json").read_text(encoding="utf-8")
        expected = json.loads(template_text.replace("~/.claude", str(self.prefix)))
        self.assertEqual(self.settings(), expected)
        claude_md = (self.prefix / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("<!-- relevo:begin -->", claude_md)
        self.assertIn("@orchestrator/policy.md", claude_md)
        self.assertIn(str(self.prefix / "orchestrator" / "docs" / "INDEX.md"), claude_md)

    def test_end_to_end_with_temporary_home(self) -> None:
        env = self.env()
        env["PYTHON"] = sys.executable
        claude = self.home / ".claude"

        def sh(script: str, *args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["sh", str(ROOT / "scripts" / script), *args],
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
                check=False,
            )

        dry = sh("install.sh", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse(claude.exists())
        done = sh("install.sh")
        self.assertEqual(done.returncode, 0, done.stderr)
        settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings, TEMPLATE)  # literal ~/.claude is kept for the default prefix
        self.assertIn("Edit(~/.claude/settings.json)", settings["permissions"]["ask"])
        again = sh("install.sh")
        self.assertEqual(again.returncode, 0)
        self.assertIn("nothing to do", again.stdout)
        gone = sh("uninstall.sh")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((claude / "settings.json").exists())
        self.assertFalse((claude / "agents" / "rapido.md").exists())

    def test_no_settings_and_no_claude_md_flags(self) -> None:
        result = self.install("--no-settings", "--no-claude-md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.prefix / "settings.json").exists())
        self.assertFalse((self.prefix / "CLAUDE.md").exists())
        self.assertTrue((self.prefix / "agents" / "rapido.md").is_file())

    def test_usage_errors_exit_2(self) -> None:
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("install", "--bogus").returncode, 2)

    def test_shell_wrappers_are_executable_and_valid(self) -> None:
        for name in ("install.sh", "uninstall.sh"):
            path = ROOT / "scripts" / name
            self.assertTrue(os.access(path, os.X_OK), name)
            self.assertEqual(subprocess.run(["sh", "-n", str(path)], check=False).returncode, 0)


class IdempotencyAndSafetyTests(InstallerCase):
    def test_second_run_changes_nothing(self) -> None:
        self.write_settings(self.USER_SETTINGS)
        (self.prefix / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
        self.assertEqual(self.install().returncode, 0)
        before = snapshot(self.prefix)
        backups_before = self.backups()
        again = self.install()
        self.assertEqual(again.returncode, 0)
        self.assertIn("nothing to do", again.stdout)
        self.assertEqual(snapshot(self.prefix), before)  # settings, CLAUDE.md and manifest byte for byte
        self.assertEqual(self.backups(), backups_before)

    def test_fresh_install_makes_no_backup(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.backups(), [])

    def test_user_settings_are_preserved(self) -> None:
        path = self.write_settings(self.USER_SETTINGS)
        original = path.read_bytes()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        merged = self.settings()
        self.assertEqual(merged["model"], "opus")
        self.assertEqual(merged["permissions"]["allow"], ["Bash(ls:*)"])
        self.assertEqual(merged["env"]["FOO"], "bar")
        self.assertEqual(merged["env"][DEPTH], "1")
        ask = merged["permissions"]["ask"]
        self.assertEqual(ask[:2], ["Bash(git push:*)", "Bash(my-tool:*)"])  # the user's order comes first
        self.assertEqual(ask.count("Bash(git push:*)"), 1)
        pre = merged["hooks"]["PreToolUse"]
        self.assertEqual(pre[0]["hooks"][0]["command"], "/usr/local/bin/mine")
        commands = [h["command"] for g in pre for h in g["hooks"]]
        self.assertIn(str(self.prefix / "hooks" / "block-force-push"), commands)
        self.assertIn(str(self.prefix / "hooks" / "guard-secrets"), commands)
        self.assertEqual(merged["hooks"]["Stop"], self.USER_SETTINGS["hooks"]["Stop"])
        self.assertTrue(merged["hooks"]["SubagentStop"][0]["hooks"][0]["async"])
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "settings.json").read_bytes(), original)

    def test_env_conflict_keeps_user_value_and_warns(self) -> None:
        self.write_settings({"env": {DEPTH: "3"}})
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.settings()["env"][DEPTH], "3")
        self.assertIn(DEPTH, result.stderr)

    def test_existing_hook_is_not_duplicated(self) -> None:
        guard = str(self.prefix / "hooks" / "guard-secrets")
        group = {"matcher": "Bash", "hooks": [{"type": "command", "command": guard}]}
        self.write_settings({"hooks": {"PreToolUse": [group]}})
        self.assertEqual(self.install().returncode, 0)
        commands = [h["command"] for g in self.settings()["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(commands.count(guard), 1)
        self.assertEqual(commands.count(str(self.prefix / "hooks" / "block-force-push")), 1)

    def test_orch_resume_is_registered_for_compact_and_resume_and_removed_on_uninstall(self) -> None:
        self.write_settings({"hooks": {"SessionStart": [{"matcher": "startup", "hooks": []}]}})
        self.assertEqual(self.install().returncode, 0)
        resume = str(self.prefix / "hooks" / "orch-resume")
        groups = self.settings()["hooks"]["SessionStart"]
        registered = {g.get("matcher"): [h["command"] for h in g["hooks"]] for g in groups}
        self.assertEqual(registered, {"startup": [], "compact": [resume], "resume": [resume]})
        self.assertTrue(all(h["timeout"] == 5 for g in groups for h in g["hooks"]))
        manifest = json.loads((self.prefix / "orchestrator" / ".relevo-manifest.json").read_text(encoding="utf-8"))
        self.assertIn("hooks/orch-resume", manifest["files"])
        recorded = [(h["matcher"], h["command"]) for h in manifest["settings_added"]["hooks"] if h["command"] == resume]
        self.assertEqual(sorted(recorded), [("compact", resume), ("resume", resume)])
        self.assertIn("nothing to do", self.install().stdout)
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertEqual(self.settings(), {"hooks": {"SessionStart": [{"matcher": "startup", "hooks": []}]}})

    def test_user_registered_orch_resume_is_left_alone(self) -> None:
        resume = str(self.prefix / "hooks" / "orch-resume")
        mine = {"hooks": {"SessionStart": [{"matcher": "compact", "hooks": [{"type": "command", "command": resume}]}]}}
        self.write_settings(mine)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.settings()["hooks"]["SessionStart"], mine["hooks"]["SessionStart"])

    def test_invalid_settings_abort_without_changes(self) -> None:
        for content in ("{ not json", "[]", '{"permissions": []}', '{"hooks": {"PreToolUse": "x"}}', '{"env": 3}'):
            with self.subTest(content=content):
                self.prefix.mkdir(parents=True, exist_ok=True)
                (self.prefix / "settings.json").write_text(content, encoding="utf-8")
                before = snapshot(self.prefix)
                result = self.install()
                self.assertEqual(result.returncode, 1)
                self.assertIn("settings.json", result.stderr)
                self.assertEqual(snapshot(self.prefix), before)

    def test_dry_run_writes_nothing_and_shows_diffs(self) -> None:
        self.write_settings(self.USER_SETTINGS)
        (self.prefix / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")
        before = snapshot(self.prefix)
        result = self.install("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(self.prefix), before)
        self.assertIn("--- a/settings.json", result.stdout)
        self.assertIn("+++ b/CLAUDE.md", result.stdout)
        self.assertFalse((self.prefix / ".relevo-backups").exists())

    def test_settings_symlink_is_kept(self) -> None:
        real = self.tmp / "dotfiles" / "settings.json"
        real.parent.mkdir()
        real.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
        real.chmod(0o600)
        self.prefix.mkdir()
        link = self.prefix / "settings.json"
        link.symlink_to(real)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(real))
        merged = json.loads(real.read_text(encoding="utf-8"))
        self.assertEqual(merged["model"], "opus")
        self.assertIn("hooks", merged)
        self.assertEqual(stat.S_IMODE(real.stat().st_mode), 0o600)

    def test_claude_md_with_import_is_left_alone(self) -> None:
        self.prefix.mkdir()
        original = "# mine\n  @orchestrator/policy.md  \nmore\n"
        (self.prefix / "CLAUDE.md").write_text(original, encoding="utf-8")
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual((self.prefix / "CLAUDE.md").read_text(encoding="utf-8"), original)
        manifest = json.loads((self.prefix / "orchestrator" / ".relevo-manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["claude_md_block"])
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertEqual((self.prefix / "CLAUDE.md").read_text(encoding="utf-8"), original)

    def test_source_that_is_not_a_checkout_fails_cleanly(self) -> None:
        fake = self.tmp / "fake" / "scripts"
        fake.mkdir(parents=True)
        shutil.copy2(INSTALLER, fake / "relevo_install.py")
        result = self.install(script=fake / "relevo_install.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not look like a relevo checkout", result.stderr)
        self.assertFalse(self.prefix.exists())


class ConflictAndUpgradeTests(InstallerCase):
    def test_foreign_agent_blocks_without_force(self) -> None:
        (self.prefix / "agents").mkdir(parents=True)
        mine = self.prefix / "agents" / "rapido.md"
        mine.write_text("my own agent\n", encoding="utf-8")
        before = snapshot(self.prefix)
        result = self.install()
        self.assertEqual(result.returncode, 1)
        self.assertIn("an agent named rapido already exists", result.stderr)
        self.assertEqual(snapshot(self.prefix), before)

    def test_force_backs_up_and_overwrites(self) -> None:
        (self.prefix / "agents").mkdir(parents=True)
        mine = self.prefix / "agents" / "rapido.md"
        mine.write_text("my own agent\n", encoding="utf-8")
        result = self.install("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mine.read_bytes(), (ROOT / "agents" / "rapido.md").read_bytes())
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "agents" / "rapido.md").read_text(encoding="utf-8"), "my own agent\n")

    def test_identical_preexisting_file_is_not_ours_and_survives_uninstall(self) -> None:
        (self.prefix / "agents").mkdir(parents=True)
        mine = self.prefix / "agents" / "verificador.md"
        mine.write_bytes((ROOT / "agents" / "verificador.md").read_bytes())  # same bytes as relevo's copy
        self.assertEqual(self.install().returncode, 0)
        manifest = json.loads((self.prefix / "orchestrator" / ".relevo-manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("agents/verificador.md", manifest["files"])
        self.assertIn("agents/rapido.md", manifest["files"])
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertTrue(mine.is_file())
        self.assertFalse((self.prefix / "agents" / "rapido.md").exists())

    def test_forced_overwrite_is_restored_by_uninstall(self) -> None:
        (self.prefix / "agents").mkdir(parents=True)
        mine = self.prefix / "agents" / "rapido.md"
        mine.write_text("my own agent\n", encoding="utf-8")
        self.assertEqual(self.install("--force").returncode, 0)
        manifest_path = self.prefix / "orchestrator" / ".relevo-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        saved = self.prefix / manifest["overwritten"]["agents/rapido.md"]
        self.assertEqual(saved.read_text(encoding="utf-8"), "my own agent\n")
        # A second run must neither lose nor change the record of the original.
        again = self.install("--force")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["overwritten"], manifest["overwritten"])
        result = self.uninstall()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mine.read_text(encoding="utf-8"), "my own agent\n")
        self.assertFalse((self.prefix / "agents" / "verificador.md").exists())

    def test_upgrade_uses_manifest_and_removes_stale_files(self) -> None:
        script = self.make_source_copy()
        src = script.parents[1]
        self.assertEqual(self.install(script=script).returncode, 0)
        # The "new release" edits an agent and stops shipping two doc files.
        with open(src / "agents" / "rapido.md", "a", encoding="utf-8") as handle:
            handle.write("\nNew line in the next release.\n")
        (src / "docs" / "GLOSSARY.md").unlink()
        (src / "docs" / "routing.md").unlink()
        routing = self.prefix / "orchestrator" / "docs" / "routing.md"
        routing.write_text(routing.read_text(encoding="utf-8") + "\nmy notes\n", encoding="utf-8")
        old_rapido = (self.prefix / "agents" / "rapido.md").read_bytes()

        result = self.install(script=script)  # no --force: the hashes match the manifest
        self.assertEqual(result.returncode, 0, result.stderr)
        upgraded = (self.prefix / "agents" / "rapido.md").read_text(encoding="utf-8")
        self.assertIn("New line in the next release", upgraded)
        self.assertFalse((self.prefix / "orchestrator" / "docs" / "GLOSSARY.md").exists())
        self.assertTrue(routing.exists())  # modified by the user: kept
        self.assertIn("routing.md", result.stderr)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "agents" / "rapido.md").read_bytes(), old_rapido)
        manifest = json.loads((self.prefix / "orchestrator" / ".relevo-manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("orchestrator/docs/GLOSSARY.md", manifest["files"])
        self.assertNotIn("orchestrator/docs/routing.md", manifest["files"])

    def test_locally_modified_managed_file_is_a_conflict(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        target = self.prefix / "commands" / "orch-stats.md"
        target.write_text(target.read_text(encoding="utf-8") + "local tweak\n", encoding="utf-8")
        script = self.make_source_copy()
        with open(script.parents[1] / "commands" / "orch-stats.md", "a", encoding="utf-8") as handle:
            handle.write("\nrelease change\n")
        result = self.install(script=script)
        self.assertEqual(result.returncode, 1)
        self.assertIn("modified after the last relevo install", result.stderr)
        self.assertIn("local tweak", target.read_text(encoding="utf-8"))


class UninstallTests(InstallerCase):
    def test_uninstall_restores_previous_state(self) -> None:
        settings_path = self.write_settings(self.USER_SETTINGS)
        settings_before = json.loads(settings_path.read_text(encoding="utf-8"))
        claude_md = self.prefix / "CLAUDE.md"
        claude_md.write_text("# my notes\n\nsome text\n", encoding="utf-8")
        claude_before = claude_md.read_bytes()
        self.assertEqual(self.install().returncode, 0)

        tweaked = self.prefix / "agents" / "rapido.md"
        tweaked.write_text(tweaked.read_text(encoding="utf-8") + "mine\n", encoding="utf-8")
        log = self.prefix / "orchestrator" / "log.jsonl"
        log.write_text('{"agent": "rapido"}\n', encoding="utf-8")

        result = self.uninstall()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.settings(), settings_before)
        self.assertEqual(claude_md.read_bytes(), claude_before)
        self.assertTrue(tweaked.exists())  # modified by the user: kept
        self.assertIn("rapido.md", result.stderr)
        self.assertFalse((self.prefix / "agents" / "verificador.md").exists())
        self.assertFalse((self.prefix / "hooks" / "guard-secrets").exists())
        self.assertFalse((self.prefix / "orchestrator" / "docs").exists())
        self.assertFalse((self.prefix / "orchestrator" / ".relevo-manifest.json").exists())
        self.assertTrue(log.exists())
        self.assertIn(str(log), result.stdout)
        self.assertTrue(self.backups())

    def test_uninstall_after_clean_install_removes_created_files(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertFalse((self.prefix / "settings.json").exists())
        self.assertFalse((self.prefix / "CLAUDE.md").exists())

    def test_uninstall_dry_run_changes_nothing(self) -> None:
        self.write_settings(self.USER_SETTINGS)
        self.assertEqual(self.install().returncode, 0)
        before = snapshot(self.prefix)
        result = self.uninstall("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(self.prefix), before)

    def test_uninstall_without_manifest_is_a_noop(self) -> None:
        result = self.uninstall()
        self.assertEqual(result.returncode, 0)
        self.assertIn("nothing to uninstall", result.stdout.lower())

    def test_uninstall_keeps_env_value_changed_by_user(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        data = self.settings()
        data["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] = "opus"
        (self.prefix / "settings.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertEqual(self.settings(), {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "opus"}})


class RegressionTests(InstallerCase):
    def test_prefix_with_spaces_and_shell_characters_keeps_hooks_working(self) -> None:
        self.prefix = self.tmp / "my prefix$HOME 'x'"
        self.assertEqual(self.install().returncode, 0)
        settings = self.settings()
        commands = [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
        self.assertEqual(len(commands), 5)  # orch-resume is registered twice (compact, resume)
        for hook in ("block-force-push", "guard-secrets", "orch-telemetry", "orch-resume"):
            self.assertIn(shlex.quote(str(self.prefix / "hooks" / hook)), commands)
        for command in commands:
            with self.subTest(command=command):
                env = self.env()
                env["ORCH_LOG"] = str(self.tmp / "log.jsonl")
                result = subprocess.run(
                    ["sh", "-c", command], input="{}", capture_output=True, text=True, env=env, timeout=30, check=False
                )
                self.assertEqual(result.returncode, 0, result.stderr)  # 127 would mean "command not found"
        # Permission rules are not shell commands: the path stays unquoted there.
        self.assertIn(f"Edit({self.prefix}/settings.json)", settings["permissions"]["ask"])
        again = self.install()
        self.assertIn("nothing to do", again.stdout)
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertFalse((self.prefix / "settings.json").exists())

    def test_user_empty_hook_group_survives_uninstall(self) -> None:
        user = {"hooks": {"PreToolUse": [{"matcher": "Mine", "hooks": []}], "Stop": [{"hooks": []}]}}
        self.write_settings(user)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertEqual(self.settings(), user)

    def test_unmerge_only_drops_groups_emptied_by_relevo(self) -> None:
        merged, added, _warn = relevo_install.merge_settings(
            {"hooks": {"PreToolUse": [{"matcher": "Mine", "hooks": []}]}}, copy.deepcopy(TEMPLATE)
        )
        cleaned = relevo_install.unmerge_settings(merged, added, ["hooks.SubagentStop", "hooks.SessionStart"])
        self.assertEqual(cleaned["hooks"], {"PreToolUse": [{"matcher": "Mine", "hooks": []}]})

    def test_claude_md_without_final_newline_round_trips(self) -> None:
        self.prefix.mkdir()
        claude_md = self.prefix / "CLAUDE.md"
        for original in (b"# mine", b"# mine\n", b"# mine\n\n", b""):
            with self.subTest(original=original):
                claude_md.write_bytes(original)
                self.assertEqual(self.install("--no-settings").returncode, 0)
                self.assertIn(b"relevo:begin", claude_md.read_bytes())
                self.assertEqual(self.uninstall().returncode, 0)
                self.assertEqual(claude_md.read_bytes(), original)


class StrictSettingsTests(InstallerCase):
    """settings.json is rewritten as plain JSON: comments and duplicate keys abort before any write."""

    REJECTED: ClassVar[dict[str, str]] = {
        "line comment": '{\n  // mine\n  "model": "opus"\n}\n',
        "block comment": '{"model": "opus" /* mine */}\n',
        "duplicate top-level key": '{"model": "opus", "model": "sonnet"}\n',
        "duplicate nested key": '{"env": {"A": "1", "A": "2"}}\n',
    }

    def test_install_refuses_comments_and_duplicate_keys_without_writing(self) -> None:
        for case, content in self.REJECTED.items():
            with self.subTest(case=case):
                self.prefix.mkdir(parents=True, exist_ok=True)
                (self.prefix / "settings.json").write_text(content, encoding="utf-8")
                before = snapshot(self.prefix)
                result = self.install()
                self.assertEqual(result.returncode, 1)
                self.assertIn("nothing was changed", result.stderr)
                self.assertIn("comment" if "comment" in case else "repeats the key", result.stderr)
                self.assertEqual(snapshot(self.prefix), before)

    def test_slashes_inside_strings_are_not_comments(self) -> None:
        self.write_settings({"apiKeyHelper": "https://example.test/*x*/", "env": {"P": 'a//b "q" //'}})
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.settings()["apiKeyHelper"], "https://example.test/*x*/")

    def test_uninstall_refuses_a_settings_file_that_gained_a_comment(self) -> None:
        self.assertEqual(self.install().returncode, 0)
        path = self.prefix / "settings.json"
        path.write_text("// added later\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
        before = snapshot(self.prefix)
        result = self.uninstall()
        self.assertEqual(result.returncode, 1)
        self.assertIn("comment on line 1", result.stderr)
        self.assertNotIn("--no-settings", result.stderr)
        self.assertEqual(snapshot(self.prefix), before)

    def test_find_comment_reports_the_line(self) -> None:
        self.assertEqual(relevo_install.find_comment('{"a": "//"}'), 0)
        self.assertEqual(relevo_install.find_comment('{"a": "\\\\"} // x'), 1)
        self.assertEqual(relevo_install.find_comment('{\n"a": 1\n/* x */}'), 3)


class BackupRetentionTests(InstallerCase):
    def setUp(self) -> None:
        super().setUp()
        self.prefix.mkdir()
        self.counter = 0

    def backup_of(self, content: str, pin: bool = False) -> Path | None:
        """Write settings.json with ``content`` and back it up as the installer would."""
        (self.prefix / "settings.json").write_text(content, encoding="utf-8")
        self.counter += 1
        root = self.prefix / ".relevo-backups" / f"20260101-0000{self.counter:02d}"
        result: Path | None = relevo_install.make_backup(self.prefix, ["settings.json"], root, pin=pin)
        return result

    def test_identical_content_reuses_the_existing_backup(self) -> None:
        first = self.backup_of("{}")
        again = self.backup_of("{}")
        self.assertEqual(again, first)
        other = self.backup_of('{"a": 1}')
        self.assertNotEqual(other, first)
        self.assertEqual(len(self.backups()), 2)
        meta = json.loads((other / ".relevo-backup.json").read_text(encoding="utf-8"))  # type: ignore[operator]
        self.assertEqual(set(meta["files"]), {"settings.json"})

    def test_manifest_install_time_does_not_defeat_deduplication(self) -> None:
        manifest = self.prefix / "orchestrator" / ".relevo-manifest.json"
        manifest.parent.mkdir()
        roots = []
        for stamp in ("2026-01-01T00:00:00", "2026-02-02T00:00:00"):
            manifest.write_text(json.dumps({"version": "x", "installed_at": stamp}), encoding="utf-8")
            self.counter += 1
            root = self.prefix / ".relevo-backups" / f"20260101-0000{self.counter:02d}"
            roots.append(relevo_install.make_backup(self.prefix, [relevo_install.MANIFEST_REL], root))
        self.assertEqual(roots[0], roots[1])

    def test_backup_edited_by_hand_is_not_reused(self) -> None:
        first = self.backup_of('{"a": 1}')
        assert first is not None
        (first / "settings.json").unlink()
        again = self.backup_of('{"a": 1}')
        self.assertNotEqual(again, first)
        self.assertEqual((again / "settings.json").read_text(encoding="utf-8"), '{"a": 1}')  # type: ignore[operator]

    def test_legacy_backup_without_metadata_is_matched_by_content(self) -> None:
        legacy = self.prefix / ".relevo-backups" / "20250101-000000"
        legacy.mkdir(parents=True)
        (legacy / "settings.json").write_text('{"old": true}', encoding="utf-8")
        self.assertEqual(self.backup_of('{"old": true}'), legacy)

    def test_keeps_the_last_five_plus_pinned_and_protected(self) -> None:
        pinned = self.backup_of('{"n": "pinned"}', pin=True)
        protected = self.backup_of('{"n": "protected"}')
        assert pinned is not None and protected is not None
        made = [self.backup_of(json.dumps({"n": n})) for n in range(7)]
        removed = relevo_install.prune_backups(self.prefix, {protected.name})
        self.assertEqual(removed, made[:2])
        self.assertEqual(self.backups(), sorted([pinned, protected, *made[2:]]))

    def test_reused_backup_counts_as_recent(self) -> None:
        oldest = self.backup_of('{"n": "oldest"}')
        for n in range(5):
            self.backup_of(json.dumps({"n": n}))
        self.assertEqual(self.backup_of('{"n": "oldest"}'), oldest)
        relevo_install.prune_backups(self.prefix, set())
        self.assertIn(oldest, self.backups())
        self.assertEqual(len(self.backups()), 5)

    def test_runs_within_one_second_keep_their_order(self) -> None:
        with mock.patch.object(relevo_install, "_stamp", return_value="20260101-000000"):
            made = [self.backup_of(json.dumps({"n": n})) for n in range(7)]
        self.assertEqual(relevo_install.list_backups(self.prefix), made)
        legacy = self.prefix / ".relevo-backups" / "20250101-000000"
        legacy.mkdir()
        (legacy / "settings.json").write_text("{}", encoding="utf-8")
        self.assertEqual(relevo_install.list_backups(self.prefix)[0], legacy)
        relevo_install.prune_backups(self.prefix, set(), current=made[-1].name)  # type: ignore[union-attr]
        self.assertEqual(relevo_install.list_backups(self.prefix), made[2:])

    def test_prune_ignores_foreign_names_and_symlinks(self) -> None:
        base = self.prefix / ".relevo-backups"
        (base / "notes").mkdir(parents=True)
        target = self.tmp / "elsewhere"
        target.mkdir()
        (base / "20000101-000000").symlink_to(target)
        for n in range(7):
            self.backup_of(json.dumps({"n": n}))
        relevo_install.prune_backups(self.prefix, set())
        self.assertTrue((base / "notes").is_dir())
        self.assertTrue(target.is_dir())
        self.assertEqual(len(relevo_install.list_backups(self.prefix)), 5)

    def test_install_never_prunes_the_backup_holding_a_forced_original(self) -> None:
        self.prefix.rmdir()
        (self.prefix / "agents").mkdir(parents=True)
        (self.prefix / "agents" / "rapido.md").write_text("my own agent\n", encoding="utf-8")
        self.assertEqual(self.install("--force").returncode, 0)
        original = self.backups()[0]
        for n in range(7):
            data = self.settings()
            data["env"]["N"] = str(n)
            (self.prefix / "settings.json").write_text(json.dumps(data), encoding="utf-8")
            (self.prefix / "CLAUDE.md").write_text(f"# {n}\n", encoding="utf-8")
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(original, self.backups())
        self.assertLessEqual(len(self.backups()), 6)
        self.assertEqual(self.uninstall().returncode, 0)
        self.assertEqual((self.prefix / "agents" / "rapido.md").read_text(encoding="utf-8"), "my own agent\n")

    def test_pin_backup_flag_and_backups_command(self) -> None:
        (self.prefix / "settings.json").write_text("{}", encoding="utf-8")
        result = self.install("--pin-backup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(pinned)", result.stdout)
        [root] = self.backups()
        self.assertTrue((root / ".pinned").exists())
        listing = self.run_cli("backups", "--prefix", str(self.prefix))
        self.assertIn(f"{root.name}  ", listing.stdout)
        self.assertIn("[pinned]", listing.stdout)
        self.assertEqual(self.run_cli("backups", "--prefix", str(self.prefix), "--unpin", root.name).returncode, 0)
        self.assertFalse((root / ".pinned").exists())
        self.assertEqual(self.run_cli("backups", "--prefix", str(self.prefix), "--pin", root.name).returncode, 0)
        self.assertTrue((root / ".pinned").exists())
        missing = self.run_cli("backups", "--prefix", str(self.prefix), "--pin", "19990101-000000")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("no backup named", missing.stderr)


class MergeUnitTests(unittest.TestCase):
    @staticmethod
    def sample_users() -> list[dict[str, Any]]:
        return [
            {},
            {"model": "x"},
            copy.deepcopy(InstallerCase.USER_SETTINGS),
            {"permissions": {"ask": ["Bash(npx:*)"]}},
        ]

    def merge(self, user: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        return relevo_install.merge_settings(user, copy.deepcopy(TEMPLATE))

    def test_empty_user_gets_the_template(self) -> None:
        merged, added, warnings = self.merge({})
        self.assertEqual(merged, TEMPLATE)
        self.assertEqual(warnings, [])
        self.assertEqual(added["env"], TEMPLATE["env"])
        self.assertEqual(len(added["hooks"]), 5)

    def test_merge_is_idempotent(self) -> None:
        users = self.sample_users()
        for user in users:
            with self.subTest(user=user):
                once, _added, _warn = self.merge(user)
                twice, added_again, _warn2 = self.merge(once)
                self.assertEqual(twice, once)
                self.assertEqual(added_again, {"env": {}, "ask": [], "deny": [], "hooks": []})

    def test_unmerge_inverts_merge(self) -> None:
        users = self.sample_users()
        for user in users:
            with self.subTest(user=user):
                merged, added, _warn = self.merge(user)
                created = relevo_install.containers_created(user, merged)
                self.assertEqual(relevo_install.unmerge_settings(merged, added, created), user)

    def test_user_does_not_lose_keys_and_input_is_not_mutated(self) -> None:
        user = copy.deepcopy(InstallerCase.USER_SETTINGS)
        frozen = copy.deepcopy(user)
        merged, _added, _warn = self.merge(user)
        self.assertEqual(user, frozen)
        self.assertEqual(merged["model"], "opus")

    def test_allow_overlap_warns(self) -> None:
        _merged, _added, warnings = self.merge({"permissions": {"allow": ["Bash(git push:*)"]}})
        self.assertTrue(any("permissions.allow" in w and "git push" in w for w in warnings))

    def test_hook_group_keeps_matcher_timeout_and_async(self) -> None:
        merged, _added, _warn = self.merge({})
        groups = merged["hooks"]["PreToolUse"]
        self.assertEqual(groups[0]["matcher"], "Bash")
        self.assertEqual(groups[0]["hooks"][0]["timeout"], 5)
        self.assertTrue(merged["hooks"]["SubagentStop"][0]["hooks"][0]["async"])

    @staticmethod
    def hook_settings(command: str) -> dict[str, Any]:
        return {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": command}]}]}}

    def test_same_command_is_compared_with_expanduser(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": "/home/someone"}):
            user = self.hook_settings("~/.claude/hooks/guard-secrets")
            tpl = self.hook_settings("/home/someone/.claude/hooks/guard-secrets")
            merged, added, _warn = relevo_install.merge_settings(user, tpl)
        self.assertEqual(merged, user)
        self.assertEqual(added["hooks"], [])

    def test_shape_errors(self) -> None:
        bad_settings: list[dict[str, Any]] = [
            {"env": []},
            {"permissions": {"ask": "x"}},
            {"hooks": []},
            {"hooks": {"Stop": [3]}},
        ]
        for bad in bad_settings:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                relevo_install.merge_settings(bad, TEMPLATE)

    def test_plan_files_skips_dotfiles_and_pycache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)
            for name in ("agents", "hooks", "commands", "orchestrator", "docs", "templates"):
                (src / name).mkdir()
            (src / "docs" / "sub").mkdir()
            (src / "docs" / "sub" / "a.md").write_text("a", encoding="utf-8")
            (src / "docs" / ".hidden.md").write_text("h", encoding="utf-8")
            (src / "docs" / "__pycache__").mkdir()
            (src / "docs" / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")
            (src / "hooks" / "tool").write_text("#!/bin/sh\n", encoding="utf-8")
            (src / "hooks" / ".DS_Store").write_text("junk", encoding="utf-8")
            for name in relevo_install.ORCHESTRATOR_FILES:
                (src / "orchestrator" / name).write_text("x", encoding="utf-8")
            plan = relevo_install.plan_files(src)
        self.assertIn("orchestrator/docs/sub/a.md", plan)
        self.assertIn("hooks/tool", plan)
        self.assertEqual(plan["hooks/tool"][1], 0o755)
        self.assertFalse([rel for rel in plan if ".hidden" in rel or "pycache" in rel or "DS_Store" in rel])


if __name__ == "__main__":
    unittest.main()
