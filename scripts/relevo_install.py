#!/usr/bin/env python3
"""relevo installer.

Copies agents, hooks, commands, the orchestrator policy and the docs into a Claude Code
config directory (default ``~/.claude``), merges the orchestrator part of ``settings.json``
and appends the policy import to ``CLAUDE.md``. Everything it changes is recorded in a
manifest so that it can be upgraded and uninstalled exactly.

Standard library only; runs on Python 3.9+.

    relevo_install.py install   [--prefix DIR] [--dry-run] [--force] [--no-settings] [--no-claude-md]
    relevo_install.py uninstall [--prefix DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import datetime
import difflib
import hashlib
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = "0.1.0"

SRC_ROOT = Path(__file__).resolve().parents[1]
BEGIN_MARK = "<!-- relevo:begin -->"
END_MARK = "<!-- relevo:end -->"
IMPORT_LINE = "@orchestrator/policy.md"
MANIFEST_REL = "orchestrator/.relevo-manifest.json"
BACKUP_DIRNAME = ".relevo-backups"
DOCS_REL = "orchestrator/docs"
DEPTH_KEY = "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"
REQUIRED_DIRS = ("agents", "hooks", "commands", "orchestrator", "docs", "templates")
ORCHESTRATOR_FILES = ("policy.md", "project-template.md", "stats.py")
LITERAL_HOME = "~/.claude"


class InstallError(Exception):
    """A fatal, user-facing problem. The message is printed and the exit code is 1."""


@dataclass
class FileOp:
    action: str  # create | update | overwrite | chmod | remove | keep | unchanged
    rel: str
    src: Path | None = None
    mode: int = 0o644
    note: str = ""


# --------------------------------------------------------------------------- helpers


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def atomic_write(path: Path, data: bytes, mode: int, follow_symlink: bool = False) -> None:
    """Write ``data`` next to ``path`` and ``os.replace`` it into place.

    With ``follow_symlink`` the real target of a symlink is written and the link is kept.
    """
    target = Path(os.path.realpath(path)) if follow_symlink else path
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".relevo-tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def existing_mode(path: Path) -> int:
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return 0o644


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def normalize_prefix(raw: str | None) -> Path:
    if raw:
        return Path(os.path.abspath(os.path.expanduser(raw)))
    return Path(os.path.expanduser("~")) / ".claude"


def is_default_prefix(prefix: Path) -> bool:
    default = Path(os.path.expanduser("~")) / ".claude"
    return os.path.realpath(prefix) == os.path.realpath(default)


def rewrite_paths(obj: Any, prefix: str) -> Any:
    """Replace the literal ``~/.claude`` in every string of a JSON-like structure."""
    if isinstance(obj, str):
        return obj.replace(LITERAL_HOME, prefix)
    if isinstance(obj, list):
        return [rewrite_paths(item, prefix) for item in obj]
    if isinstance(obj, dict):
        return {key: rewrite_paths(value, prefix) for key, value in obj.items()}
    return obj


def quote_hook_command(command: str, prefix: str) -> str:
    """Point a hook command at ``prefix``, shell-quoting the path (hook commands run through a shell)."""
    head, sep, rest = command.partition(" ")
    if head == LITERAL_HOME or head.startswith(LITERAL_HOME + "/"):
        head = shlex.quote(prefix + head[len(LITERAL_HOME) :])
    return head + sep + rest


def rewrite_template(tpl: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Rewrite ``~/.claude`` to ``prefix``: quoted inside hook commands, plain everywhere else."""
    out: dict[str, Any] = {}
    for key, value in tpl.items():
        if key != "hooks":
            out[key] = rewrite_paths(value, prefix)
            continue
        hooks = copy.deepcopy(value)
        for groups in hooks.values():
            for group in groups:
                for hook in group.get("hooks", []):
                    if isinstance(hook.get("command"), str):
                        hook["command"] = quote_hook_command(hook["command"], prefix)
        out[key] = hooks
    return out


def unified_diff(name: str, old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{name}",
        tofile=f"b/{name}",
    )
    out = "".join(line if line.endswith("\n") else line + "\n" for line in lines)
    return out


# --------------------------------------------------------------------------- settings.json


def check_settings_shape(settings: Any) -> None:
    """Raise ``ValueError`` if the parts of settings.json that relevo touches have unexpected types."""
    if not isinstance(settings, dict):
        raise ValueError("top-level value must be a JSON object")
    if "env" in settings and not isinstance(settings["env"], dict):
        raise ValueError('"env" must be an object')
    if "permissions" in settings:
        perms = settings["permissions"]
        if not isinstance(perms, dict):
            raise ValueError('"permissions" must be an object')
        for key in ("allow", "ask", "deny"):
            if key in perms and not isinstance(perms[key], list):
                raise ValueError(f'"permissions.{key}" must be an array')
    if "hooks" in settings:
        hooks = settings["hooks"]
        if not isinstance(hooks, dict):
            raise ValueError('"hooks" must be an object')
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                raise ValueError(f'"hooks.{event}" must be an array')
            for group in groups:
                if not isinstance(group, dict):
                    raise ValueError(f'"hooks.{event}" must contain objects')
                inner = group.get("hooks", [])
                if not isinstance(inner, list) or not all(isinstance(h, dict) for h in inner):
                    raise ValueError(f'"hooks.{event}[].hooks" must be an array of objects')


def _same_command(first: Any, second: Any) -> bool:
    if not isinstance(first, str) or not isinstance(second, str):
        return False
    return first == second or os.path.expanduser(first) == os.path.expanduser(second)


def merge_settings(user: dict[str, Any], tpl: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Merge the relevo template into the user's settings without overriding anything.

    Returns ``(merged, added, warnings)``. ``added`` records exactly what was inserted:
    ``{"env": {k: v}, "ask": [...], "deny": [...], "hooks": [{"event", "matcher", "command"}]}``.
    """
    try:
        check_settings_shape(user)
    except ValueError as exc:
        raise ValueError(f"settings.json: {exc}") from exc
    merged = copy.deepcopy(user)
    added: dict[str, Any] = {"env": {}, "ask": [], "deny": [], "hooks": []}
    warnings: list[str] = []

    for key, value in tpl.get("env", {}).items():
        current = merged.get("env", {})
        if key not in current:
            merged.setdefault("env", {})[key] = value
            added["env"][key] = value
        elif current[key] != value:
            extra = " (relevo needs 1 so that workers cannot spawn subagents)" if key == DEPTH_KEY else ""
            warnings.append(f"env.{key} is {current[key]!r}; keeping your value, relevo recommends {value!r}{extra}")

    tpl_perms = tpl.get("permissions", {})
    for key in ("deny", "ask"):
        for entry in tpl_perms.get(key, []):
            if entry in merged.get("permissions", {}).get(key, []):
                pass
            else:
                merged.setdefault("permissions", {}).setdefault(key, []).append(entry)
                added[key].append(entry)
            if entry in merged.get("permissions", {}).get("allow", []):
                warnings.append(f"permissions.allow contains {entry!r}, which relevo lists under {key}; review it")

    for event, groups in tpl.get("hooks", {}).items():
        present = [
            hook.get("command") for group in merged.get("hooks", {}).get(event, []) for hook in group.get("hooks", [])
        ]
        for group in groups:
            new_hooks = []
            for hook in group.get("hooks", []):
                command = hook.get("command")
                if any(_same_command(command, other) for other in present):
                    continue
                new_hooks.append(copy.deepcopy(hook))
                present.append(command)
            if not new_hooks:
                continue
            new_group = {key: copy.deepcopy(value) for key, value in group.items() if key != "hooks"}
            new_group["hooks"] = new_hooks
            merged.setdefault("hooks", {}).setdefault(event, []).append(new_group)
            for hook in new_hooks:
                added["hooks"].append({"event": event, "matcher": group.get("matcher"), "command": hook.get("command")})
    return merged, added, warnings


def containers_created(user: dict[str, Any], merged: dict[str, Any]) -> list[str]:
    """Names of the containers (``env``, ``hooks.PreToolUse``...) that the merge had to create."""
    created: list[str] = [key for key in ("env", "permissions", "hooks") if key not in user and key in merged]
    user_perms = user.get("permissions", {})
    merged_perms = merged.get("permissions", {})
    created += [f"permissions.{key}" for key in ("deny", "ask") if key not in user_perms and key in merged_perms]
    user_hooks = user.get("hooks", {})
    created += [f"hooks.{event}" for event in merged.get("hooks", {}) if event not in user_hooks]
    return created


def unmerge_settings(
    user: dict[str, Any], added: dict[str, Any], created: tuple[str, ...] | list[str] = ()
) -> dict[str, Any]:
    """Remove exactly what ``merge_settings`` recorded in ``added``; drop empty containers listed in ``created``."""
    out = copy.deepcopy(user)
    env = out.get("env")
    if isinstance(env, dict):
        for key, value in added.get("env", {}).items():
            if key in env and env[key] == value:
                del env[key]
    perms = out.get("permissions")
    if isinstance(perms, dict):
        for key in ("ask", "deny"):
            if isinstance(perms.get(key), list):
                drop = set(added.get(key, []))
                perms[key] = [entry for entry in perms[key] if entry not in drop]
    hooks = out.get("hooks")
    if isinstance(hooks, dict):
        for item in added.get("hooks", []):
            groups = hooks.get(item["event"])
            if not isinstance(groups, list):
                continue
            emptied: list[int] = []
            for group in groups:
                if not isinstance(group, dict) or group.get("matcher") != item.get("matcher"):
                    continue
                inner = group.get("hooks")
                if isinstance(inner, list):
                    kept = [hook for hook in inner if hook.get("command") != item["command"]]
                    if len(kept) != len(inner):
                        group["hooks"] = kept
                        if not kept:
                            emptied.append(id(group))
            # Drop only the groups that relevo left empty, never empty groups the user already had.
            hooks[item["event"]] = [g for g in groups if id(g) not in emptied]
    # Empty containers that the installation itself created.
    for name in created:
        parts = name.split(".")
        if len(parts) == 2 and isinstance(out.get(parts[0]), dict) and out[parts[0]].get(parts[1]) in ([], {}):
            del out[parts[0]][parts[1]]
    for name in created:
        if "." not in name and out.get(name) == {}:
            del out[name]
    return out


# --------------------------------------------------------------------------- CLAUDE.md


def claude_block(template_text: str) -> str:
    return f"{BEGIN_MARK}\n{template_text.rstrip()}\n{END_MARK}"


def plan_claude_md(existing: str | None, template_text: str) -> tuple[str | None, bool]:
    """Return ``(new_text_or_None_if_unchanged, relevo_owns_a_block)``."""
    if existing is not None:
        if BEGIN_MARK in existing:
            return None, True
        if any(line.strip() == IMPORT_LINE for line in existing.splitlines()):
            return None, False
    base = existing or ""
    if base and not base.endswith("\n"):
        base += "\n"
    if base:
        base += "\n"
    return base + claude_block(template_text) + "\n", True


def remove_claude_block(text: str, added_newline: bool = False) -> str:
    """Undo ``plan_claude_md``. ``added_newline``: the original file had no final newline and install added one."""
    start = text.find(BEGIN_MARK)
    end = text.find(END_MARK, start + 1) if start != -1 else -1
    if start == -1 or end == -1:
        return text
    end += len(END_MARK)
    if text[end : end + 1] == "\n":
        end += 1
    if text[max(0, start - 2) : start] == "\n\n":
        start -= 1
    result = text[:start] + text[end:]
    if added_newline and result.endswith("\n"):
        result = result[:-1]
    return result


# --------------------------------------------------------------------------- files and manifest


def preflight(src: Path, prefix: Path) -> list[str]:
    """Check the environment; raise ``InstallError`` on fatal problems and return soft warnings."""
    warnings: list[str] = []
    if os.name == "nt":
        raise InstallError("native Windows is not supported; use WSL")
    # Runtime guard for interpreters older than the declared floor (ruff targets py39, hence the noqa).
    if sys.version_info < (3, 9):  # noqa: UP036
        raise InstallError("Python 3.9 or newer is required")
    missing = [name for name in REQUIRED_DIRS if not (src / name).is_dir()]
    if missing:
        raise InstallError(f"{src} does not look like a relevo checkout (missing: {', '.join(missing)})")
    for name in ORCHESTRATOR_FILES:
        if not (src / "orchestrator" / name).is_file():
            raise InstallError(f"missing source file orchestrator/{name}")
    for name in ("settings.example.json", "CLAUDE.md.example"):
        if not (src / "templates" / name).is_file():
            raise InstallError(f"missing source file templates/{name}")
    exe = shutil.which("python3")
    if exe is None:
        warnings.append("python3 not found in PATH; the hooks use '#!/usr/bin/env python3' and will not run")
    else:
        try:
            result = subprocess.run(
                [exe, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            major, minor = (int(part) for part in result.stdout.strip().split("."))
            if (major, minor) < (3, 9):
                warnings.append(f"python3 in PATH is {major}.{minor}; the hooks need 3.9 or newer")
        except (OSError, ValueError, subprocess.SubprocessError):
            warnings.append("could not determine the version of python3 in PATH; the hooks need 3.9 or newer")
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir and os.path.realpath(os.path.expanduser(config_dir)) != os.path.realpath(prefix):
        warnings.append(
            f"CLAUDE_CONFIG_DIR is set to {config_dir}; the hooks and stats.py assume ~/.claude, "
            f"so installing into {prefix} may not take effect"
        )
    return warnings


def plan_files(src: Path) -> dict[str, tuple[Path, int]]:
    """Map destination path (relative to the prefix) to ``(source file, mode)``."""
    plan: dict[str, tuple[Path, int]] = {}

    def add(rel: str, path: Path, mode: int) -> None:
        plan[rel] = (path, mode)

    for path in sorted((src / "agents").glob("*.md")):
        add(f"agents/{path.name}", path, 0o644)
    for path in sorted((src / "hooks").iterdir()):
        if path.is_file() and not path.name.startswith(".") and path.suffix != ".pyc":
            add(f"hooks/{path.name}", path, 0o755)
    for path in sorted((src / "commands").glob("*.md")):
        add(f"commands/{path.name}", path, 0o644)
    for name in ORCHESTRATOR_FILES:
        add(f"orchestrator/{name}", src / "orchestrator" / name, 0o644)
    docs = src / "docs"
    for dirpath, dirnames, filenames in os.walk(docs):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
        for filename in sorted(filenames):
            if filename.startswith(".") or filename.endswith(".pyc"):
                continue
            path = Path(dirpath) / filename
            rel = path.relative_to(docs).as_posix()
            add(f"{DOCS_REL}/{rel}", path, 0o644)
    return dict(sorted(plan.items()))


def classify_files(
    plan: dict[str, tuple[Path, int]],
    prefix: Path,
    old_files: dict[str, str],
    force: bool,
) -> tuple[list[FileOp], list[str]]:
    """Decide what to do with every file. Returns ``(ops, conflicts)``."""
    ops: list[FileOp] = []
    conflicts: list[str] = []
    for rel, (src, mode) in plan.items():
        dest = prefix / rel
        if not os.path.lexists(dest):
            ops.append(FileOp("create", rel, src, mode))
            continue
        if dest.is_dir() and not dest.is_symlink():
            conflicts.append(f"{dest} is a directory")
            continue
        try:
            current = sha256_file(dest)
        except OSError as exc:
            conflicts.append(f"cannot read {dest}: {exc}")
            continue
        wanted = sha256_file(src)
        if current == wanted:
            if mode & 0o111 and not os.access(dest, os.X_OK):
                ops.append(FileOp("chmod", rel, src, mode))
            else:
                ops.append(FileOp("unchanged", rel, src, mode))
        elif old_files.get(rel) == current:
            ops.append(FileOp("update", rel, src, mode))
        elif force:
            ops.append(FileOp("overwrite", rel, src, mode))
        else:
            if rel.startswith("agents/"):
                name = Path(rel).stem
                reason = f"an agent named {name} already exists in {prefix / 'agents'}"
            elif rel in old_files:
                reason = f"{dest} was modified after the last relevo install"
            else:
                reason = f"{dest} already exists with different content and is not managed by relevo"
            conflicts.append(reason)
    return ops, conflicts


def stale_ops(plan: dict[str, tuple[Path, int]], prefix: Path, old_files: dict[str, str]) -> list[FileOp]:
    """Files of the previous manifest that this version no longer ships."""
    ops: list[FileOp] = []
    for rel, digest in sorted(old_files.items()):
        if rel in plan:
            continue
        dest = prefix / rel
        if not os.path.lexists(dest):
            continue
        try:
            same = sha256_file(dest) == digest
        except OSError:
            same = False
        if same:
            ops.append(FileOp("remove", rel, note="no longer distributed"))
        else:
            ops.append(FileOp("keep", rel, note="no longer distributed but modified by you"))
    return ops


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(read_text(path))
    except (OSError, ValueError) as exc:
        raise InstallError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("files", {}), dict):
        raise InstallError(f"manifest {path} has an unexpected format")
    return data


def _union(first: list[Any], second: list[Any]) -> list[Any]:
    out = list(first)
    out.extend(item for item in second if item not in out)
    return out


def merge_added(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Union of two ``settings_added`` records."""
    env = dict(old.get("env", {}))
    env.update({key: value for key, value in new.get("env", {}).items() if key not in env})
    return {
        "env": env,
        "ask": _union(old.get("ask", []), new.get("ask", [])),
        "deny": _union(old.get("deny", []), new.get("deny", [])),
        "hooks": _union(old.get("hooks", []), new.get("hooks", [])),
    }


def pick_backup_root(prefix: Path) -> Path:
    """Name of a backup directory that does not exist yet (it is created only if something is saved)."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = prefix / BACKUP_DIRNAME
    root = base / stamp
    counter = 1
    while root.exists():
        root = base / f"{stamp}-{counter}"
        counter += 1
    return root


def make_backup(prefix: Path, rels: list[str], root: Path) -> Path | None:
    existing = [rel for rel in rels if os.path.lexists(prefix / rel)]
    if not existing:
        return None
    for rel in existing:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prefix / rel, target)
    return root


def restore_or_remove(prefix: Path, rel: str, overwritten: dict[str, str]) -> None:
    """Put back the user's original file saved by ``--force`` if there is one; otherwise delete relevo's copy."""
    dest = prefix / rel
    saved = overwritten.get(rel)
    if saved and os.path.lexists(prefix / saved):
        original = prefix / saved
        atomic_write(dest, original.read_bytes(), existing_mode(original))
        return
    if saved:
        warn(f"{rel}: the backup of your original file ({saved}) is missing; it cannot be restored")
    dest.unlink()


def _report(op: FileOp) -> str:
    suffix = f"  ({op.note})" if op.note else ""
    return f"  {op.action:<9} {op.rel}{suffix}"


# --------------------------------------------------------------------------- install


def do_install(prefix: Path, *, dry_run: bool, force: bool, no_settings: bool, no_claude_md: bool) -> int:
    src = SRC_ROOT
    for message in preflight(src, prefix):
        warn(message)
    default = is_default_prefix(prefix)
    prefix_text = str(prefix)

    manifest_path = prefix / MANIFEST_REL
    old_manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            old_manifest = load_manifest(manifest_path)
        except InstallError as exc:
            warn(f"{exc}; treating this as a fresh install")
    old_files: dict[str, str] = dict(old_manifest.get("files", {}))

    # Files.
    plan = plan_files(src)
    ops, conflicts = classify_files(plan, prefix, old_files, force)
    if conflicts and not force:
        for conflict in conflicts:
            print(f"error: {conflict}", file=sys.stderr)
        print("error: nothing was changed; re-run with --force to back up and overwrite", file=sys.stderr)
        return 1
    if conflicts:  # directories cannot be overwritten even with --force
        for conflict in conflicts:
            print(f"error: {conflict}", file=sys.stderr)
        return 1
    ops += stale_ops(plan, prefix, old_files)

    # settings.json.
    settings_path = prefix / "settings.json"
    settings_old_text: str | None = None
    settings_new_text: str | None = None
    added: dict[str, Any] = {"env": {}, "ask": [], "deny": [], "hooks": []}
    created: list[str] = []
    if not no_settings:
        user: dict[str, Any] = {}
        if os.path.exists(settings_path):
            settings_old_text = read_text(settings_path)
            try:
                loaded = json.loads(settings_old_text)
            except ValueError as exc:
                raise InstallError(f"{settings_path} is not valid JSON ({exc}); fix it and re-run") from exc
            if not isinstance(loaded, dict):
                raise InstallError(f"{settings_path}: top-level value must be a JSON object")
            user = loaded
        tpl = json.loads(read_text(src / "templates" / "settings.example.json"))
        if not default:
            tpl = rewrite_template(tpl, prefix_text)
        try:
            merged, added, setting_warnings = merge_settings(user, tpl)
        except ValueError as exc:
            raise InstallError(f"{settings_path}: {exc}") from exc
        for message in setting_warnings:
            warn(message)
        if merged != user:
            settings_new_text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
            created = containers_created(user, merged)
            if settings_old_text is None:
                created.append("settings.json")

    # CLAUDE.md.
    claude_path = prefix / "CLAUDE.md"
    claude_old_text: str | None = None
    claude_new_text: str | None = None
    claude_block_owned = bool(old_manifest.get("claude_md_block", False))
    claude_added_newline = bool(old_manifest.get("claude_md_added_newline", False))
    if not no_claude_md:
        if os.path.exists(claude_path):
            claude_old_text = read_text(claude_path)
        template_text = read_text(src / "templates" / "CLAUDE.md.example")
        if not default:
            template_text = template_text.replace(LITERAL_HOME, prefix_text)
        claude_new_text, claude_block_owned = plan_claude_md(claude_old_text, template_text)
        if claude_new_text is not None and claude_old_text is None:
            created.append("CLAUDE.md")
        if claude_new_text is not None and claude_old_text and not claude_old_text.endswith("\n"):
            claude_added_newline = True  # uninstall must take that newline out again

    # Manifest.
    old_created = list(old_manifest.get("created_containers", []))
    backup_root = pick_backup_root(prefix)

    def managed(op: FileOp) -> bool:
        # Files that were already in the prefix before relevo (identical copies) are not ours: never recorded,
        # so uninstall cannot delete them.
        if op.action in ("create", "update", "overwrite"):
            return True
        return op.action in ("unchanged", "chmod") and op.rel in old_files

    managed_files = {op.rel: sha256_file(plan[op.rel][0]) for op in ops if op.rel in plan and managed(op)}
    saved_originals = {
        op.rel: (backup_root / op.rel).relative_to(prefix).as_posix() for op in ops if op.action == "overwrite"
    }
    saved_originals.update(dict(old_manifest.get("overwritten", {})))  # the first backup is the real original
    manifest: dict[str, Any] = {
        "version": VERSION,
        "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": managed_files,
        "overwritten": {rel: path for rel, path in sorted(saved_originals.items()) if rel in managed_files},
        "settings_added": merge_added(old_manifest.get("settings_added", {}), added),
        "created_containers": _union(old_created, created),
        "claude_md_block": claude_block_owned,
        "claude_md_added_newline": claude_added_newline,
    }
    for op in ops:
        if op.action == "keep":
            warn(f"{op.rel}: {op.note}; leaving it in place")

    def stable(data: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in data.items() if key != "installed_at"}

    file_changes = [op for op in ops if op.action not in ("unchanged", "keep")]
    manifest_changed = stable(manifest) != stable(old_manifest)
    if not (file_changes or settings_new_text or claude_new_text or manifest_changed):
        print(f"relevo {VERSION} is already installed in {prefix}; nothing to do.")
        return 0

    verb = "would install" if dry_run else "installing"
    print(f"relevo {VERSION}: {verb} into {prefix}")
    for op in file_changes:
        print(_report(op))
    unchanged = sum(1 for op in ops if op.action == "unchanged")
    if unchanged:
        print(f"  ({unchanged} files already up to date)")
    if settings_new_text is not None:
        print(f"  {'merge':<9} settings.json")
    if claude_new_text is not None:
        print(f"  {'update':<9} CLAUDE.md")
    if dry_run:
        if settings_new_text is not None:
            print(unified_diff("settings.json", settings_old_text or "", settings_new_text), end="")
        if claude_new_text is not None:
            print(unified_diff("CLAUDE.md", claude_old_text or "", claude_new_text), end="")
        print("Dry run: nothing was written.")
        return 0

    # Backup everything that is about to be overwritten or modified.
    backup_rels = [op.rel for op in file_changes if op.action in ("update", "overwrite", "remove")]
    if settings_new_text is not None:
        backup_rels.append("settings.json")
    if claude_new_text is not None:
        backup_rels.append("CLAUDE.md")
    backup_rels.append(MANIFEST_REL)
    backup = make_backup(prefix, backup_rels, backup_root)
    old_overwritten: dict[str, str] = dict(old_manifest.get("overwritten", {}))

    for op in file_changes:
        dest = prefix / op.rel
        if op.action in ("create", "update", "overwrite") and op.src is not None:
            atomic_write(dest, op.src.read_bytes(), op.mode)
        elif op.action == "chmod":
            os.chmod(dest, op.mode)
        elif op.action == "remove":
            restore_or_remove(prefix, op.rel, old_overwritten)
    (prefix / "orchestrator").mkdir(parents=True, exist_ok=True)
    if settings_new_text is not None:
        mode = existing_mode(settings_path) if os.path.exists(settings_path) else 0o644
        atomic_write(settings_path, settings_new_text.encode("utf-8"), mode, follow_symlink=True)
    if claude_new_text is not None:
        mode = existing_mode(claude_path) if os.path.exists(claude_path) else 0o644
        atomic_write(claude_path, claude_new_text.encode("utf-8"), mode, follow_symlink=True)
    atomic_write(manifest_path, (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"), 0o644)

    if backup is not None:
        print(f"Backup of replaced files: {backup}")
    hint = "" if default else f" --prefix {prefix}"
    print("Done. Next steps:")
    print("  1. Restart Claude Code (settings and hooks are read at session start).")
    print("  2. Run /agents and check that the six relevo agents are listed.")
    print("  3. Optional, per project: run /orchestrator-init.")
    print("  4. Later, run /orch-stats to see the telemetry summary.")
    print(f"To uninstall: ./scripts/uninstall.sh{hint}")
    return 0


# --------------------------------------------------------------------------- uninstall


def do_uninstall(prefix: Path, *, dry_run: bool) -> int:
    manifest_path = prefix / MANIFEST_REL
    if not manifest_path.exists():
        print(f"No relevo manifest at {manifest_path}; nothing to uninstall.")
        return 0
    manifest = load_manifest(manifest_path)
    files: dict[str, str] = dict(manifest.get("files", {}))
    created = list(manifest.get("created_containers", []))
    overwritten: dict[str, str] = dict(manifest.get("overwritten", {}))

    ops: list[FileOp] = []
    for rel, digest in sorted(files.items()):
        dest = prefix / rel
        if not os.path.lexists(dest):
            continue
        try:
            same = sha256_file(dest) == digest
        except OSError:
            same = False
        if same and rel in overwritten and os.path.lexists(prefix / overwritten[rel]):
            ops.append(FileOp("restore", rel, note="your original file comes back"))
        elif same:
            ops.append(FileOp("remove", rel))
        else:
            ops.append(FileOp("keep", rel, note="modified since install"))

    settings_path = prefix / "settings.json"
    settings_old_text: str | None = None
    settings_new_text: str | None = None
    delete_settings = False
    if os.path.exists(settings_path):
        settings_old_text = read_text(settings_path)
        try:
            user = json.loads(settings_old_text)
            check_settings_shape(user)
        except ValueError as exc:
            raise InstallError(f"{settings_path}: {exc}; fix it and re-run") from exc
        cleaned = unmerge_settings(user, manifest.get("settings_added", {}), created)
        if cleaned != user:
            if cleaned == {} and "settings.json" in created:
                delete_settings = True
            else:
                settings_new_text = json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n"

    claude_path = prefix / "CLAUDE.md"
    claude_old_text: str | None = None
    claude_new_text: str | None = None
    delete_claude = False
    if manifest.get("claude_md_block") and os.path.exists(claude_path):
        claude_old_text = read_text(claude_path)
        stripped = remove_claude_block(claude_old_text, bool(manifest.get("claude_md_added_newline")))
        if stripped != claude_old_text:
            if not stripped.strip() and "CLAUDE.md" in created:
                delete_claude = True
            else:
                claude_new_text = stripped

    verb = "would uninstall" if dry_run else "uninstalling"
    print(f"relevo: {verb} from {prefix}")
    for op in ops:
        if op.action in ("remove", "restore"):
            print(_report(op))
        else:
            warn(f"{op.rel}: {op.note}; keeping it")
    if settings_new_text is not None or delete_settings:
        print(f"  {'unmerge':<9} settings.json")
    if claude_new_text is not None or delete_claude:
        print(f"  {'unmerge':<9} CLAUDE.md")
    if dry_run:
        if settings_old_text is not None and (settings_new_text is not None or delete_settings):
            print(unified_diff("settings.json", settings_old_text, settings_new_text or ""), end="")
        if claude_old_text is not None and (claude_new_text is not None or delete_claude):
            print(unified_diff("CLAUDE.md", claude_old_text, claude_new_text or ""), end="")
        print("Dry run: nothing was changed.")
        return 0

    backup_rels = [op.rel for op in ops if op.action in ("remove", "restore")] + [MANIFEST_REL]
    if settings_new_text is not None or delete_settings:
        backup_rels.append("settings.json")
    if claude_new_text is not None or delete_claude:
        backup_rels.append("CLAUDE.md")
    backup = make_backup(prefix, backup_rels, pick_backup_root(prefix))

    for op in ops:
        if op.action in ("remove", "restore"):
            restore_or_remove(prefix, op.rel, overwritten)
    docs_dir = prefix / DOCS_REL
    if docs_dir.is_dir():
        for dirpath, _dirnames, _filenames in os.walk(docs_dir, topdown=False):
            with contextlib.suppress(OSError):
                os.rmdir(dirpath)  # fails (and is ignored) unless the directory is empty
    if settings_new_text is not None:
        mode = existing_mode(settings_path)
        atomic_write(settings_path, settings_new_text.encode("utf-8"), mode, follow_symlink=True)
    elif delete_settings:
        os.unlink(settings_path)
    if claude_new_text is not None:
        mode = existing_mode(claude_path)
        atomic_write(claude_path, claude_new_text.encode("utf-8"), mode, follow_symlink=True)
    elif delete_claude:
        os.unlink(claude_path)
    manifest_path.unlink()

    if backup is not None:
        print(f"Backup of removed or modified files: {backup}")
    log = prefix / "orchestrator" / "log.jsonl"
    if log.exists():
        print(f"Kept your telemetry log: {log}")
    print("Done. Restart Claude Code to apply the change.")
    return 0


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="relevo_install.py",
        description="Install or remove relevo (multi-model orchestrator for Claude Code).",
    )
    parser.add_argument("--version", action="version", version=f"relevo {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="install or upgrade relevo")
    install.add_argument("--prefix", metavar="DIR", help="target directory (default: ~/.claude)")
    install.add_argument("--dry-run", action="store_true", help="show what would change and write nothing")
    install.add_argument("--force", action="store_true", help="back up and overwrite conflicting files")
    install.add_argument("--no-settings", action="store_true", help="do not touch settings.json")
    install.add_argument("--no-claude-md", action="store_true", help="do not touch CLAUDE.md")

    uninstall = sub.add_parser("uninstall", help="remove what the manifest says relevo installed")
    uninstall.add_argument("--prefix", metavar="DIR", help="target directory (default: ~/.claude)")
    uninstall.add_argument("--dry-run", action="store_true", help="show what would change and write nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prefix = normalize_prefix(args.prefix)
    try:
        if os.name == "nt":
            raise InstallError("native Windows is not supported; use WSL")
        if args.command == "install":
            return do_install(
                prefix,
                dry_run=args.dry_run,
                force=args.force,
                no_settings=args.no_settings,
                no_claude_md=args.no_claude_md,
            )
        return do_uninstall(prefix, dry_run=args.dry_run)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
