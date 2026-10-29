#!/usr/bin/env python3
"""relevo doctor: read-only diagnosis of a relevo installation.

Each check has a stable id, a status (pass, warn or fail) and, when it does not pass, a remedy. The doctor
only reads files (and runs ``python3 --version``); it never applies a remedy. Exit code: 1 if any check
fails, 0 otherwise, 2 on bad arguments.

    doctor.py [--prefix DIR] [--project DIR] [--json]

Standard library only; runs on Python 3.9+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

MANIFEST_REL = "orchestrator/.relevo-manifest.json"
AGENTS = ("Explore", "arquitecto", "clasificador", "implementador", "rapido", "verificador")
COMMANDS = ("orch-doctor", "orch-stats", "orchestrator-init")
HOOKS = ("block-force-push", "guard-secrets", "orch-resume", "orch-telemetry")
# (event, values the matcher must cover, hook). Kept equal to templates/settings.example.json by the tests.
EXPECTED_HOOKS = (
    ("PreToolUse", ("Bash",), "block-force-push"),
    ("PreToolUse", ("Bash", "Grep", "Read"), "guard-secrets"),
    ("SubagentStop", (), "orch-telemetry"),
    ("SessionStart", ("compact", "resume"), "orch-resume"),
)
ENV_REQUIRED = {"CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1"}
ENV_RECOMMENDED = {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}
MODELS = ("haiku", "sonnet", "opus", "inherit")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SHEBANG = "#!/usr/bin/env python3"
IMPORT_LINE = "@orchestrator/policy.md"
# Same pattern as hooks/orch-resume (tests keep them equal).
IGNORED = re.compile(r"(?m)^\s*/?\.claude/(work/?|work/\*\*?|\*)?\s*$")
FRONTMATTER_LINE = re.compile(r"^([A-Za-z][\w-]*):\s*(.*)$")
STATUSES = ("pass", "warn", "fail")


@dataclass
class Result:
    id: str
    status: str
    message: str
    remedy: str = ""
    details: list[str] = field(default_factory=list)


@dataclass
class Context:
    prefix: Path
    project: Path
    git_root: Path | None
    script_dir: Path


def ok(check_id: str, message: str) -> Result:
    return Result(check_id, "pass", message)


def worst(results: list[str]) -> str:
    return max(results, key=STATUSES.index) if results else "pass"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_root(path: Path) -> Path | None:
    current = path.resolve()
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings(prefix: Path) -> tuple[dict[str, Any] | None, str]:
    """``(settings, error)``: the parsed ``settings.json`` or a reason it cannot be used."""
    path = prefix / "settings.json"
    if not path.is_file():
        return None, f"no existe {path}"
    try:
        data = load_json(path)
    except (OSError, ValueError) as exc:
        return None, f"{path} no es JSON válido ({exc})"
    if not isinstance(data, dict):
        return None, f"{path}: el valor raíz no es un objeto"
    return data, ""


def load_manifest(prefix: Path) -> tuple[dict[str, Any] | None, str]:
    path = prefix / MANIFEST_REL
    if not path.is_file():
        return None, ""
    try:
        data = load_json(path)
    except (OSError, ValueError) as exc:
        return None, f"no se puede leer {path} ({exc})"
    if not isinstance(data, dict) or not isinstance(data.get("files", {}), dict):
        return None, f"{path} tiene un formato inesperado"
    return data, ""


def reinstall_hint(ctx: Context) -> str:
    return f"reinstala relevo: ./scripts/install.sh --prefix {shlex.quote(str(ctx.prefix))} (desde el repo)"


# --------------------------------------------------------------------------- python:version


def check_python(ctx: Context) -> Result:
    cid = "python:version"
    running = f"{sys.version_info[0]}.{sys.version_info[1]}"
    # Runtime guard for interpreters older than the declared floor (ruff targets py39, hence the noqa).
    if sys.version_info < (3, 9):  # noqa: UP036
        return Result(cid, "fail", f"Python {running}; relevo necesita 3.9 o superior", "instala Python 3.9+")
    exe = shutil.which("python3")
    if exe is None:
        return Result(
            cid,
            "fail",
            "python3 no está en el PATH; los hooks usan '#!/usr/bin/env python3' y no se ejecutarán",
            "instala Python 3.9+ y asegúrate de que `python3` está en el PATH de Claude Code",
        )
    try:
        out = subprocess.run(
            [exe, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
        major, minor = (int(part) for part in out.split("."))
    except (OSError, ValueError, subprocess.SubprocessError):
        return Result(
            cid, "warn", f"no se pudo saber la versión de {exe}", "ejecuta `python3 --version` y comprueba ≥3.9"
        )
    if (major, minor) < (3, 9):
        return Result(
            cid, "fail", f"python3 del PATH ({exe}) es {major}.{minor}; los hooks necesitan 3.9+", "instala Python 3.9+"
        )
    return ok(cid, f"Python {running}; python3 del PATH: {major}.{minor} ({exe})")


# --------------------------------------------------------------------------- frontmatter:valid


def parse_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    """Return ``(fields, errors)`` for the ``---`` block that must open the file."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["no empieza por '---'"]
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, ["falta el '---' de cierre"]
    fields: dict[str, str] = {}
    errors: list[str] = []
    for number, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = FRONTMATTER_LINE.match(line)
        if not match:
            errors.append(f"línea {number} no es 'clave: valor'")
            continue
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key in fields:
            errors.append(f"clave repetida {key!r}")
        fields[key] = value
    return fields, errors


def agent_errors(name: str, fields: dict[str, str]) -> list[str]:
    errors = []
    if fields.get("name") != name:
        errors.append(f"name es {fields.get('name')!r}, debe ser {name!r}")
    if not fields.get("description"):
        errors.append("falta description")
    model = fields.get("model", "")
    if model not in MODELS and not model.startswith("claude-"):
        errors.append(f"model {model!r} no es {', '.join(MODELS)} ni un id claude-*")
    if "effort" in fields and fields["effort"] not in EFFORTS:
        errors.append(f"effort {fields['effort']!r} no es {', '.join(EFFORTS)}")
    turns = fields.get("maxTurns", "")
    if not turns.isdigit() or int(turns) < 1:
        errors.append(f"maxTurns {turns!r} no es un entero positivo (es el tope por llamada de §3)")
    return errors


def managed(ctx: Context, folder: str, defaults: tuple[str, ...]) -> list[str]:
    """Names of the relevo files in ``folder``: from the manifest if there is one, else the shipped names."""
    manifest, _ = load_manifest(ctx.prefix)
    if manifest:
        names = [Path(rel).stem for rel in manifest.get("files", {}) if rel.startswith(f"{folder}/")]
        if names:
            return sorted(names)
    return list(defaults)


def check_frontmatter(ctx: Context) -> Result:
    cid = "frontmatter:valid"
    problems: list[str] = []
    for folder, names in (("agents", managed(ctx, "agents", AGENTS)), ("commands", managed(ctx, "commands", COMMANDS))):
        for name in names:
            path = ctx.prefix / folder / f"{name}.md"
            try:
                fields, errors = parse_frontmatter(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"{folder}/{name}.md: no se puede leer ({exc.__class__.__name__})")
                continue
            if folder == "agents":
                errors += agent_errors(name, fields)
            elif not fields.get("description"):
                errors.append("falta description")
            problems += [f"{folder}/{name}.md: {error}" for error in errors]
    if problems:
        return Result(
            cid,
            "fail",
            f"{len(problems)} problema(s) en el frontmatter de agentes o comandos",
            "corrige el frontmatter indicado o " + reinstall_hint(ctx),
            problems,
        )
    shadowed = [
        name
        for name in AGENTS
        if (ctx.project / ".claude" / "agents" / f"{name}.md").exists() and ctx.project != ctx.prefix
    ]
    if shadowed:
        return Result(
            cid,
            "warn",
            "agentes de proyecto con nombre de worker pisan a los globales (policy §8): " + ", ".join(shadowed),
            "renombra o borra esos archivos en .claude/agents/ del proyecto si no quieres que sustituyan a relevo",
        )
    return ok(cid, "frontmatter de agentes y comandos correcto")


# --------------------------------------------------------------------------- hooks:executable


def check_hooks_executable(ctx: Context) -> Result:
    cid = "hooks:executable"
    fails: list[str] = []
    warns: list[str] = []
    for name in HOOKS:
        path = ctx.prefix / "hooks" / name
        try:
            info = os.lstat(path)
        except OSError:
            fails.append(f"{name}: no existe")
            continue
        if not stat.S_ISREG(info.st_mode):
            fails.append(f"{name}: no es un archivo regular")
            continue
        if not os.access(path, os.X_OK):
            fails.append(f"{name}: no es ejecutable")
        if info.st_mode & stat.S_IWOTH:
            fails.append(f"{name}: cualquier usuario puede modificarlo (o+w)")
        try:
            with open(path, encoding="utf-8") as handle:
                first = handle.readline().strip()
        except (OSError, UnicodeDecodeError):
            first = ""
        if first != SHEBANG:
            warns.append(f"{name}: la primera línea no es {SHEBANG!r}")
    if fails:
        return Result(
            cid,
            "fail",
            "hooks ausentes, no ejecutables o modificables por otros",
            f"chmod 755 {shlex.quote(str(ctx.prefix / 'hooks'))}/<hook> o " + reinstall_hint(ctx),
            fails + warns,
        )
    if warns:
        return Result(cid, "warn", "hooks con shebang inesperado", reinstall_hint(ctx), warns)
    return ok(cid, f"{len(HOOKS)} hooks presentes y ejecutables")


# --------------------------------------------------------------------------- hooks:registered


def matcher_covers(matcher: Any, value: str) -> bool:
    if matcher in (None, "", "*"):
        return True
    if not isinstance(matcher, str):
        return False
    try:
        if re.fullmatch(matcher, value):
            return True
    except re.error:
        pass
    return value in matcher.split("|")


def points_to(command: Any, target: Path) -> bool:
    if not isinstance(command, str):
        return False
    try:
        head = shlex.split(command)[0]
    except (ValueError, IndexError):
        return False
    return os.path.realpath(os.path.expanduser(head)) == os.path.realpath(target)


def disabled_by(ctx: Context, settings: dict[str, Any]) -> list[str]:
    """Settings files that set ``disableAllHooks``: the user's and the project's."""
    found = ["settings.json"] if settings.get("disableAllHooks") is True else []
    if ctx.project != ctx.prefix:
        for name in ("settings.json", "settings.local.json"):
            path = ctx.project / ".claude" / name
            try:
                data = load_json(path)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and data.get("disableAllHooks") is True:
                found.append(str(path))
    return found


def check_hooks_registered(ctx: Context) -> Result:
    cid = "hooks:registered"
    settings, error = load_settings(ctx.prefix)
    if settings is None:
        return Result(cid, "fail", error, reinstall_hint(ctx))
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    missing: list[str] = []
    for event, values, name in EXPECTED_HOOKS:
        target = ctx.prefix / "hooks" / name
        groups = hooks.get(event)
        groups = [g for g in groups if isinstance(g, dict)] if isinstance(groups, list) else []
        for value in values or ("",):
            registered = any(
                (not values or matcher_covers(group.get("matcher"), value))
                and any(
                    isinstance(h, dict)
                    and h.get("type", "command") == "command"
                    and points_to(h.get("command"), target)
                    for h in (group.get("hooks") if isinstance(group.get("hooks"), list) else [])
                )
                for group in groups
            )
            if not registered:
                missing.append(f"{event}" + (f" ({value})" if value else "") + f" → {name}")
    disabled = disabled_by(ctx, settings)
    details = missing + [f"disableAllHooks: true en {path}" for path in disabled]
    if details:
        return Result(
            cid,
            "fail",
            "hay hooks de relevo sin registrar o desactivados",
            "quita disableAllHooks y " + reinstall_hint(ctx) + " (fusiona settings.json sin pisar lo tuyo)",
            details,
        )
    return ok(cid, "hooks registrados, incluido orch-resume en SessionStart compact y resume")


# --------------------------------------------------------------------------- env


def check_env(ctx: Context) -> Result:
    cid = "env"
    settings, error = load_settings(ctx.prefix)
    if settings is None:
        return Result(cid, "fail", error, reinstall_hint(ctx))
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    assert isinstance(env, dict)
    fails = [
        f"{key} es {env.get(key)!r}, debe ser {value!r}" for key, value in ENV_REQUIRED.items() if env.get(key) != value
    ]
    warns = [
        f"{key} es {env.get(key)!r}; relevo recomienda {value!r}"
        for key, value in ENV_RECOMMENDED.items()
        if env.get(key) != value
    ]
    for key, value in ENV_REQUIRED.items():
        current = os.environ.get(key)
        if current is not None and current != value:
            warns.append(f"la variable de entorno {key}={current!r} de esta shell puede pisar settings.json")
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir and os.path.realpath(os.path.expanduser(config_dir)) != os.path.realpath(ctx.prefix):
        warns.append(f"CLAUDE_CONFIG_DIR apunta a {config_dir}, no a {ctx.prefix}")
    if fails:
        return Result(
            cid,
            "fail",
            "env de settings.json no impide que los workers lancen subagentes",
            'pon "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1" en env de settings.json',
            fails + warns,
        )
    if warns:
        return Result(cid, "warn", "env distinto de lo recomendado", "revisa env en settings.json y tu shell", warns)
    return ok(cid, "env correcto (profundidad de subagentes 1)")


# --------------------------------------------------------------------------- manifest:drift


def present(settings: dict[str, Any] | None, key: str, entry: str) -> bool:
    perms = settings.get("permissions") if settings else None
    values = perms.get(key) if isinstance(perms, dict) else None
    return isinstance(values, list) and entry in values


def check_manifest(ctx: Context) -> Result:
    cid = "manifest:drift"
    manifest, error = load_manifest(ctx.prefix)
    if error:
        return Result(cid, "fail", error, reinstall_hint(ctx))
    if manifest is None:
        return Result(
            cid,
            "warn",
            f"no hay manifest en {ctx.prefix / MANIFEST_REL}: relevo no se instaló con el instalador",
            reinstall_hint(ctx),
        )
    fails: list[str] = []
    warns: list[str] = []
    for rel, digest in sorted(dict(manifest.get("files", {})).items()):
        path = ctx.prefix / rel
        if not path.exists():
            fails.append(f"falta {rel}")
            continue
        try:
            if sha256_file(path) != digest:
                warns.append(f"modificado desde la instalación: {rel}")
        except OSError as exc:
            fails.append(f"no se puede leer {rel} ({exc.__class__.__name__})")
    settings, _ = load_settings(ctx.prefix)
    added = manifest.get("settings_added") if isinstance(manifest.get("settings_added"), dict) else {}
    assert isinstance(added, dict)
    for entry in added.get("deny", []):
        if not present(settings, "deny", entry):
            fails.append(f"permissions.deny ya no contiene {entry!r}")
    for entry in added.get("ask", []):
        if not present(settings, "ask", entry):
            warns.append(f"permissions.ask ya no contiene {entry!r}")
    version = manifest.get("version", "?")
    if fails:
        return Result(
            cid, "fail", f"la instalación {version} no coincide con su manifest", reinstall_hint(ctx), fails + warns
        )
    if warns:
        return Result(
            cid,
            "warn",
            f"{len(warns)} cambio(s) desde la instalación {version}",
            "si no son tuyos, " + reinstall_hint(ctx) + " con --force (guarda copia de lo que pisa)",
            warns,
        )
    return ok(cid, f"{len(manifest.get('files', {}))} archivos coinciden con el manifest ({version})")


# --------------------------------------------------------------------------- claude-md:import


def has_line(path: Path, line: str) -> bool:
    try:
        return any(current.strip() == line for current in path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return False


def check_claude_md(ctx: Context) -> Result:
    cid = "claude-md:import"
    claude_md = ctx.prefix / "CLAUDE.md"
    if not has_line(claude_md, IMPORT_LINE):
        return Result(
            cid,
            "fail",
            f"{claude_md} no importa la política ({IMPORT_LINE})",
            f"añade la línea {IMPORT_LINE} a {claude_md} o " + reinstall_hint(ctx),
        )
    if not (ctx.prefix / "orchestrator" / "policy.md").is_file():
        return Result(cid, "fail", "falta orchestrator/policy.md: el import no carga nada", reinstall_hint(ctx))
    project_config = ctx.project / ".claude" / "orchestrator.md"
    if ctx.project != ctx.prefix and project_config.is_file():
        imported = has_line(ctx.project / "CLAUDE.md", "@.claude/orchestrator.md") or has_line(
            ctx.project / ".claude" / "CLAUDE.md", "@orchestrator.md"
        )
        if not imported:
            return Result(
                cid,
                "warn",
                f"{project_config} existe pero el CLAUDE.md del proyecto no lo importa",
                "ejecuta /orchestrator-init o añade @.claude/orchestrator.md al CLAUDE.md de la raíz",
            )
        return ok(cid, "CLAUDE.md global importa la política y el del proyecto su .claude/orchestrator.md")
    return ok(cid, f"{claude_md} importa la política")


# --------------------------------------------------------------------------- gitignore:work


def check_gitignore(ctx: Context) -> Result:
    cid = "gitignore:work"
    if ctx.git_root is None:
        return ok(cid, f"{ctx.project} no está en un repo git: no aplica")
    gitignore = ctx.git_root / ".gitignore"
    try:
        ignored = bool(IGNORED.search(gitignore.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError):
        ignored = False
    if not ignored:
        return Result(
            cid,
            "warn",
            f".claude/work/ no está en {gitignore}: planes y logbooks pueden acabar en git y orch-resume no reinyecta",
            "ejecuta /orchestrator-init o añade `.claude/work/` al .gitignore de la raíz",
        )
    return ok(cid, f".claude/work/ ignorado en {gitignore}")


# --------------------------------------------------------------------------- routing:sync


def load_renderer(ctx: Context) -> ModuleType | None:
    """``render_routing`` next to this script (installed) or, only in a repository checkout, in ``scripts/``.

    Compiled in memory: an import would write ``__pycache__`` into the prefix, and the doctor only reads.
    """
    paths = [ctx.script_dir / "render_routing.py"]
    if not (ctx.script_dir / ".relevo-manifest.json").exists():
        paths.append(ctx.script_dir.parent / "scripts" / "render_routing.py")
    for path in paths:
        if path.is_file():
            module = ModuleType("relevo_render_routing")
            module.__file__ = str(path)
            exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
            return module
    return None


def check_routing(ctx: Context) -> Result:
    cid = "routing:sync"
    renderer = load_renderer(ctx)
    if renderer is None or not (ctx.prefix / "orchestrator" / "routing.json").is_file():
        return Result(
            cid,
            "warn",
            "faltan orchestrator/routing.json o render_routing.py: instalación anterior a /orch-doctor",
            reinstall_hint(ctx),
        )
    try:
        data = renderer.load(ctx.prefix)
        stale = []
        for rel, body in renderer.targets(data).items():
            text = (ctx.prefix / rel).read_text(encoding="utf-8")
            if renderer.replace_block(text, body, rel) != text:
                stale.append(rel)
    except (renderer.RoutingError, OSError, UnicodeDecodeError) as exc:
        return Result(cid, "fail", f"no se puede comprobar la tabla B: {exc}", reinstall_hint(ctx))
    if stale:
        return Result(
            cid,
            "fail",
            "la tabla B instalada no coincide con routing.json",
            "no edites el texto entre <!-- relevo:routing:begin/end -->; " + reinstall_hint(ctx),
            stale,
        )
    return ok(cid, "tabla B de policy.md y clasificador.md coincide con routing.json")


CHECKS: tuple[Callable[[Context], Result], ...] = (
    check_python,
    check_frontmatter,
    check_hooks_executable,
    check_hooks_registered,
    check_env,
    check_manifest,
    check_claude_md,
    check_gitignore,
    check_routing,
)
CHECK_IDS = (
    "python:version",
    "frontmatter:valid",
    "hooks:executable",
    "hooks:registered",
    "env",
    "manifest:drift",
    "claude-md:import",
    "gitignore:work",
    "routing:sync",
)


def run_checks(ctx: Context) -> list[Result]:
    results = []
    for check_id, check in zip(CHECK_IDS, CHECKS):
        try:
            results.append(check(ctx))
        except Exception as exc:  # one broken check must not hide the others
            results.append(
                Result(check_id, "fail", f"error interno del doctor: {exc!r}", "abre un issue con esta salida")
            )
    return results


def default_prefix(script_dir: Path) -> Path:
    if script_dir.name == "orchestrator" and (script_dir / ".relevo-manifest.json").is_file():
        return script_dir.parent
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(os.path.expanduser(config_dir))
    return Path(os.path.expanduser("~")) / ".claude"


def render(ctx: Context, results: list[Result]) -> str:
    lines = [f"relevo doctor — prefix {ctx.prefix}, proyecto {ctx.project}"]
    width = max(len(r.id) for r in results)
    for result in results:
        lines.append(f"{result.status:<4}  {result.id:<{width}}  {result.message}")
        lines += [f"{'':<6}{'':<{width}}  - {detail}" for detail in result.details]
        if result.remedy and result.status != "pass":
            lines.append(f"{'':<6}{'':<{width}}  remedio: {result.remedy}")
    counts = {status: sum(r.status == status for r in results) for status in STATUSES}
    lines.append(
        f"Resumen: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail. No se ha cambiado nada."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Diagnóstico de solo lectura de una instalación de relevo.")
    parser.add_argument("--prefix", metavar="DIR", help="directorio de Claude Code (por defecto ~/.claude)")
    parser.add_argument("--project", metavar="DIR", help="proyecto a revisar (por defecto el directorio actual)")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    args = parser.parse_args(argv)
    prefix = Path(os.path.abspath(os.path.expanduser(args.prefix))) if args.prefix else default_prefix(script_dir)
    project = Path(os.path.abspath(os.path.expanduser(args.project or os.getcwd())))
    ctx = Context(prefix=prefix, project=project, git_root=git_root(project), script_dir=script_dir)
    results = run_checks(ctx)
    if args.json:
        print(
            json.dumps(
                {"prefix": str(prefix), "project": str(project), "checks": [asdict(r) for r in results]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render(ctx, results))
    return 1 if worst([r.status for r in results]) == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
