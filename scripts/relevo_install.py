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
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = "0.2.0"

SRC_ROOT = Path(__file__).resolve().parents[1]
BEGIN_MARK = "<!-- relevo:begin -->"
END_MARK = "<!-- relevo:end -->"
IMPORT_LINE = "@orchestrator/policy.md"
MANIFEST_REL = "orchestrator/.relevo-manifest.json"
BACKUP_DIRNAME = ".relevo-backups"
BACKUP_META = ".relevo-backup.json"
BACKUP_PIN = ".pinned"
BACKUP_KEEP = 5
BACKUP_NAME = re.compile(r"^(\d{8}-\d{6})(?:-(\d+))?$")
STAMP_FORMAT = "%Y%m%d-%H%M%S"
DOCS_REL = "orchestrator/docs"
DEPTH_KEY = "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"
REQUIRED_DIRS = ("agents", "hooks", "commands", "orchestrator", "docs", "templates")
ORCHESTRATOR_FILES = ("policy.md", "project-template.md", "stats.py", "doctor.py", "routing.json")
# Installed next to doctor.py, which reuses it for the routing:sync check.
SCRIPT_FILES = {"orchestrator/render_routing.py": "scripts/render_routing.py"}
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


def find_comment(text: str) -> int:
    """Line number of the first ``//`` or ``/*`` outside a JSON string, or 0 if there is none."""
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "/" and text[index + 1 : index + 2] in ("/", "*"):
            return text.count("\n", 0, index) + 1
    return 0


class DuplicateKeyError(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateKeyError(key)
        seen[key] = value
    return seen


def parse_settings(text: str, path: Path, skip_hint: bool = True) -> Any:
    """Parse settings.json strictly: relevo rewrites it as plain JSON, so it refuses whatever would be lost.

    Comments (JSONC) and duplicate keys raise ``InstallError`` before anything is written.
    """
    alternative = " or re-run with --no-settings" if skip_hint else " and re-run"
    line = find_comment(text)
    if line:
        raise InstallError(
            f"{path} has a comment on line {line}; relevo rewrites settings.json as plain JSON and would drop it. "
            f"Remove the comments{alternative} (nothing was changed)"
        )
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except DuplicateKeyError as exc:
        raise InstallError(
            f"{path} repeats the key {exc.key!r}; only one of them would survive a rewrite. "
            f"Remove the duplicate{alternative} (nothing was changed)"
        ) from exc
    except ValueError as exc:
        raise InstallError(f"{path} is not valid JSON ({exc}); fix it and re-run") from exc


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
        # A command the user already registers for this event (under any matcher) is left alone. The template
        # itself may list one command under several matchers (orch-resume: SessionStart "compact" and "resume").
        present = [
            hook.get("command") for group in merged.get("hooks", {}).get(event, []) for hook in group.get("hooks", [])
        ]
        inserted: list[tuple[Any, Any]] = []
        for group in groups:
            matcher = group.get("matcher")
            new_hooks = []
            for hook in group.get("hooks", []):
                command = hook.get("command")
                if any(_same_command(command, other) for other in present) or (matcher, command) in inserted:
                    continue
                new_hooks.append(copy.deepcopy(hook))
                inserted.append((matcher, command))
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
    for source in SCRIPT_FILES.values():
        if not (src / source).is_file():
            raise InstallError(f"missing source file {source}")
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
    for rel, source in SCRIPT_FILES.items():
        add(rel, src / source, 0o644)
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


def _stamp() -> str:
    return datetime.datetime.now().strftime(STAMP_FORMAT)


def pick_backup_root(prefix: Path) -> Path:
    """Name of a backup directory that does not exist yet (it is created only if something is saved)."""
    stamp = _stamp()
    base = prefix / BACKUP_DIRNAME
    root = base / stamp
    counter = 1
    while root.exists():
        root = base / f"{stamp}-{counter}"
        counter += 1
    return root


def backup_digest(path: Path, rel: str) -> str:
    """sha256 of a file for backup deduplication; the manifest is compared without its install time."""
    data = path.read_bytes()
    if rel == MANIFEST_REL:
        with contextlib.suppress(ValueError):
            manifest = json.loads(data.decode("utf-8"))
            if isinstance(manifest, dict):
                manifest.pop("installed_at", None)
                data = json.dumps(manifest, sort_keys=True).encode("utf-8")
    return sha256_bytes(data)


def backup_checksum(files: dict[str, str]) -> str:
    """Checksum of a backup set: its relative paths and the sha256 of each file."""
    return sha256_bytes(json.dumps(sorted(files.items())).encode("utf-8"))


def list_backups(prefix: Path) -> list[Path]:
    """Backup directories created by relevo, oldest first by last use (symlinks and other names are ignored)."""
    base = prefix / BACKUP_DIRNAME
    if base.is_symlink() or not base.is_dir():
        return []
    found = [p for p in base.iterdir() if BACKUP_NAME.match(p.name) and p.is_dir() and not p.is_symlink()]
    return sorted(found, key=_backup_order)


def _backup_order(root: Path) -> tuple[int, int]:
    """Time of last use in nanoseconds (for a backup made before 0.3.0, its name's stamp), then the name counter.

    Nanoseconds and not the one-second stamp of the name: several runs within one second must keep their order.
    """
    match = BACKUP_NAME.match(root.name)
    assert match is not None
    used_ns = backup_meta(root).get("used_ns")
    if not isinstance(used_ns, int) or isinstance(used_ns, bool):
        used_ns = int(datetime.datetime.strptime(match.group(1), STAMP_FORMAT).timestamp()) * 10**9
    return used_ns, int(match.group(2) or 0)


def backup_meta(root: Path) -> dict[str, Any]:
    """The metadata of a backup; for a backup made before 0.3.0 it is computed from its files."""
    try:
        data = json.loads(read_text(root / BACKUP_META))
        if isinstance(data, dict) and isinstance(data.get("checksum"), str):
            return data
    except (OSError, ValueError):
        pass
    files: dict[str, str] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            rel = path.relative_to(root).as_posix()
            if rel in (BACKUP_META, BACKUP_PIN):
                continue
            with contextlib.suppress(OSError):
                files[rel] = backup_digest(path, rel)
    return {"checksum": backup_checksum(files), "files": files}


def backup_intact(root: Path, files: dict[str, str]) -> bool:
    """True if ``root`` still holds every file of ``files`` with that digest (it may have been edited by hand)."""
    for rel, digest in files.items():
        path = root / rel
        try:
            if path.is_symlink() or backup_digest(path, rel) != digest:
                return False
        except OSError:
            return False
    return True


def is_pinned(root: Path) -> bool:
    return (root / BACKUP_PIN).exists()


def set_pinned(root: Path, pinned: bool) -> None:
    marker = root / BACKUP_PIN
    if pinned:
        atomic_write(marker, b"pinned by relevo_install.py; never deleted by the retention policy\n", 0o644)
    elif marker.exists():
        marker.unlink()


def write_backup_meta(root: Path, meta: dict[str, Any]) -> None:
    data = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    atomic_write(root / BACKUP_META, data, 0o644)


def make_backup(prefix: Path, rels: list[str], root: Path, pin: bool = False) -> Path | None:
    """Copy ``rels`` under ``root``; if an existing backup has exactly the same content, reuse it instead.

    Returns the directory that holds the copies (``root`` or the reused one), or ``None`` if nothing existed.
    """
    existing = [rel for rel in rels if os.path.lexists(prefix / rel)]
    if not existing:
        return None
    files = {rel: backup_digest(prefix / rel, rel) for rel in existing}
    checksum = backup_checksum(files)
    for old in reversed(list_backups(prefix)):
        meta = backup_meta(old)
        if meta.get("checksum") == checksum and backup_intact(old, files):
            write_backup_meta(old, {**meta, "last_used": _stamp(), "used_ns": time.time_ns()})  # recent again
            if pin:
                set_pinned(old, True)
            return old
    for rel in existing:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prefix / rel, target)
    meta = {"checksum": checksum, "created": _stamp(), "last_used": _stamp(), "used_ns": time.time_ns(), "files": files}
    write_backup_meta(root, meta)
    if pin:
        set_pinned(root, True)
    return root


def backups_in_use(prefix: Path, *manifests: dict[str, Any]) -> set[str]:
    """Names of the backups that hold an original file a manifest will restore on uninstall."""
    names: set[str] = set()
    for manifest in manifests:
        for saved in dict(manifest.get("overwritten", {})).values():
            parts = Path(str(saved)).parts
            if len(parts) >= 2 and parts[0] == BACKUP_DIRNAME:
                names.add(parts[1])
    return names


def prune_backups(prefix: Path, protect: set[str], keep: int = BACKUP_KEEP, current: str = "") -> list[Path]:
    """Keep the ``keep`` most recently used unpinned backups.

    Pinned backups and those in ``protect`` (they hold an original a manifest will restore) do not count and are
    never deleted; ``current``, the backup this run made or reused, counts but is never deleted either.
    """
    candidates = [p for p in list_backups(prefix) if not is_pinned(p) and p.name not in protect]
    doomed = [p for p in candidates[: max(0, len(candidates) - keep)] if p.name != current]
    for root in doomed:
        shutil.rmtree(root)
    return doomed


def finish_backup(prefix: Path, backup: Path | None, protect: set[str]) -> None:
    for root in prune_backups(prefix, protect, current=backup.name if backup is not None else ""):
        print(f"  removed old backup {root.name} (keeping the last {BACKUP_KEEP} and the pinned ones)")


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


def do_install(
    prefix: Path, *, dry_run: bool, force: bool, no_settings: bool, no_claude_md: bool, pin_backup: bool = False
) -> int:
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
            loaded = parse_settings(settings_old_text, settings_path)
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
    backup = make_backup(prefix, backup_rels, backup_root, pin=pin_backup)
    if backup is not None and backup != backup_root:
        # An identical backup already existed and was reused: point the new originals at it.
        old_rel = backup_root.relative_to(prefix).as_posix() + "/"
        new_rel = backup.relative_to(prefix).as_posix() + "/"
        manifest["overwritten"] = {
            rel: new_rel + path[len(old_rel) :] if path.startswith(old_rel) else path
            for rel, path in manifest["overwritten"].items()
        }
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

    finish_backup(prefix, backup, backups_in_use(prefix, old_manifest, manifest))
    if backup is not None:
        print(f"Backup of replaced files: {backup}{' (pinned)' if pin_backup else ''}")
    hint = "" if default else f" --prefix {prefix}"
    print("Done. Next steps:")
    print("  1. Restart Claude Code (settings and hooks are read at session start).")
    print("  2. Run /agents and check that the six relevo agents are listed.")
    print("  3. Optional, per project: run /orchestrator-init.")
    print("  4. Run /orch-doctor to check the installation (read-only).")
    print("  5. Later, run /orch-stats to see the telemetry summary.")
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
        user = parse_settings(settings_old_text, settings_path, skip_hint=False)
        try:
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

    finish_backup(prefix, backup, set())
    if backup is not None:
        print(f"Backup of removed or modified files: {backup}")
    log = prefix / "orchestrator" / "log.jsonl"
    if log.exists():
        print(f"Kept your telemetry log: {log}")
    print("Done. Restart Claude Code to apply the change.")
    return 0


# --------------------------------------------------------------------------- backups


def do_backups(prefix: Path, *, pin: str | None, unpin: str | None) -> int:
    found = {root.name: root for root in list_backups(prefix)}
    name = pin or unpin
    if name is not None:
        if name not in found:
            raise InstallError(f"no backup named {name!r} in {prefix / BACKUP_DIRNAME}")
        set_pinned(found[name], pin is not None)
        print(f"{'pinned' if pin else 'unpinned'} {name}")
        return 0
    if not found:
        print(f"No backups in {prefix / BACKUP_DIRNAME}.")
        return 0
    in_use: set[str] = set()
    manifest_path = prefix / MANIFEST_REL
    if manifest_path.exists():
        in_use = backups_in_use(prefix, load_manifest(manifest_path))
    print(f"Backups in {prefix / BACKUP_DIRNAME} (newest last; the last {BACKUP_KEEP} unpinned ones are kept):")
    for root in found.values():
        tags = [tag for tag, on in (("pinned", is_pinned(root)), ("holds an original", root.name in in_use)) if on]
        files = len(backup_meta(root).get("files", {}))
        print(f"  {root.name}  {files} files{'  [' + ', '.join(tags) + ']' if tags else ''}")
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
    install.add_argument("--pin-backup", action="store_true", help="never delete the backup this run makes")

    uninstall = sub.add_parser("uninstall", help="remove what the manifest says relevo installed")
    uninstall.add_argument("--prefix", metavar="DIR", help="target directory (default: ~/.claude)")
    uninstall.add_argument("--dry-run", action="store_true", help="show what would change and write nothing")

    backups = sub.add_parser("backups", help=f"list backups; the last {BACKUP_KEEP} and the pinned ones are kept")
    backups.add_argument("--prefix", metavar="DIR", help="target directory (default: ~/.claude)")
    group = backups.add_mutually_exclusive_group()
    group.add_argument("--pin", metavar="NAME", help="keep this backup forever")
    group.add_argument("--unpin", metavar="NAME", help="let the retention policy delete this backup again")
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
                pin_backup=args.pin_backup,
            )
        if args.command == "backups":
            return do_backups(prefix, pin=args.pin, unpin=args.unpin)
        return do_uninstall(prefix, dry_run=args.dry_run)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
