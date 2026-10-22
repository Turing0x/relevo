#!/usr/bin/env python3
"""Classify the files of a pull request and render a review comment.

Used by .github/workflows/sensitive-paths.yml, which runs under
``pull_request_target``. This script therefore treats everything it reads as
untrusted DATA: it never executes, imports or evaluates anything from the pull
request, and everything that ends up in the comment is neutralized first (code
fences longer than any backtick run, escaped HTML, hidden Unicode made visible).

Input: the output of ``GET /repos/{repo}/pulls/{n}/files``, as a JSON array, an
array of arrays (``gh api --paginate --slurp``) or JSON lines. Each element needs
at least ``filename``; ``status``, ``additions``, ``deletions``, ``patch`` and
``previous_filename`` are used when present.

Output: a Markdown comment (``--out``) and, for ``$GITHUB_OUTPUT``
(``--github-output``), ONLY ``sensitive=true|false`` and ``count=N``. No content
from the pull request is ever written there.

Exit status: 0 on success, 1 on invalid input, 2 on invalid usage.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from typing import Any

MARKER = "<!-- relevo:sensitive-paths -->"
DEFAULT_REPO = "Turing0x/relevo"

# Single source of truth for security-sensitive paths. .github/CODEOWNERS lists
# the same globs one by one (tests/test_sensitive_diff.py enforces that).
SENSITIVE_GLOBS: tuple[str, ...] = (
    ".claude/**",
    "**/.claude/**",
    "**/.claude.json",
    "**/CLAUDE.md",
    "**/AGENTS.md",
    "agents/**",
    "hooks/**",
    "commands/**",
    "orchestrator/**",
    "templates/**",
    "scripts/**",
    ".github/**",
    "**/settings*.json",
    "**/.mcp.json",
    "**/*mcp*.json",
    "Makefile",
    "pyproject.toml",
    "requirements*.txt",
    ".gitattributes",
    "**/.gitleaks.toml",
    "**/.gitleaksignore",
)

COMMENT_LIMIT = 60000  # GitHub's hard limit is 65536 characters
API_FILE_LIMIT = 3000  # the files endpoint never returns more than this
MAX_TABLE_ROWS = 200
MAX_NAME_CHARS = 120
MAX_LINE_CHARS = 400
MAX_PATCH_LINES = 200
MAX_WARNINGS = 50

# Hidden or bidirectional characters (kept in sync with scripts/check_hidden_unicode.py).
HIDDEN_RE = re.compile("[\xad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

AGENT_KEYS_RE = re.compile(
    r"^[+-]\s*(name|model|effort|maxTurns|tools|disallowedTools|omitClaudeMd|permissionMode"
    r"|mcpServers|hooks|skills|memory|isolation)\s*:"
)
COMMAND_KEYS_RE = re.compile(r"^[+-]\s*(allowed-tools|model|disable-model-invocation)\s*:")
SETTINGS_TOKENS = (
    "Bash(",
    "Read(",
    "Edit(",
    "Write(",
    "WebFetch",
    "mcp__",
    '"allow"',
    '"ask"',
    '"deny"',
    '"defaultMode"',
    '"command"',
    '"matcher"',
    '"env"',
    "CLAUDE_CODE_",
    '"hooks"',
    '"permissions"',
    '"apiKeyHelper"',
    "enableAllProjectMcpServers",
)
WORKFLOW_TOKENS = (
    "permissions",
    "write",
    "pull_request_target",
    "workflow_run",
    "secrets.",
    "uses:",
    "GITHUB_TOKEN",
    "id-token",
)
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    out: list[str] = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    body = "".join(out)
    if "/" not in glob:
        # Like gitignore/CODEOWNERS: a pattern without a slash matches at any depth.
        body = "(?:.*/)?" + body
    # Case-insensitive on purpose: macOS checkouts are case-insensitive, so
    # `claude.md` would be loaded like `CLAUDE.md`. A false positive costs nothing.
    return re.compile(body, re.IGNORECASE | re.DOTALL)


_SENSITIVE_RES = tuple(_glob_to_regex(g) for g in SENSITIVE_GLOBS)


def _normalize(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def is_sensitive(path: str) -> bool:
    """Return True when ``path`` (repo-relative, '/'-separated) is security-sensitive."""
    norm = _normalize(path)
    return any(rx.fullmatch(norm) for rx in _SENSITIVE_RES)


def _matches(path: str, *globs: str) -> bool:
    norm = _normalize(path)
    return any(_glob_to_regex(g).fullmatch(norm) for g in globs)


def parse_files(text: str) -> list[dict[str, Any]]:
    """Parse the three accepted input shapes; raise ValueError on anything else."""
    stripped = text.strip()
    if not stripped:
        return []
    items: list[Any]
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        items = list(data)
    else:
        items = []
        for number, line in enumerate(stripped.splitlines(), 1):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {number}: {exc}") from exc
    flat: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, list):  # --slurp: one array per page
            for sub in item:
                flat.append(_check_entry(sub))
        else:
            flat.append(_check_entry(item))
    return flat


def _check_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str) or not entry["filename"]:
        raise ValueError("every element must be an object with a non-empty 'filename' string")
    return entry


def hidden_codepoints(text: str) -> list[str]:
    """Return the sorted distinct hidden code points (as ``U+XXXX``) found in ``text``."""
    return sorted({f"U+{ord(ch):04X}" for ch in HIDDEN_RE.findall(text)})


def _visible(text: str) -> str:
    """Make hidden characters and control characters visible, never interpretable."""
    text = HIDDEN_RE.sub(lambda m: f"<U+{ord(m.group()):04X}>", text)
    return CONTROL_RE.sub("?", text)


def _code_span(name: str) -> str:
    """Render a file name as an inline code span that cannot break out or break a table."""
    clean = _visible(name).replace("`", "'").replace("|", "\\|")
    if len(clean) > MAX_NAME_CHARS:
        clean = clean[: MAX_NAME_CHARS - 3] + "..."
    return f"`{clean}`"


def _fence_for(content: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _clip(line: str) -> str:
    line = _visible(line)
    return line if len(line) <= MAX_LINE_CHARS else line[: MAX_LINE_CHARS - 3] + "..."


def _changed_lines(patch: str) -> list[str]:
    return [ln for ln in patch.splitlines() if ln[:1] in ("+", "-") and not ln.startswith(("+++", "---"))]


def _count(patch: str) -> tuple[int, int]:
    lines = _changed_lines(patch)
    return sum(1 for ln in lines if ln[0] == "+"), sum(1 for ln in lines if ln[0] == "-")


def _int(value: Any, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default


def _status(value: Any) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[a-z_]{1,20}", value) else "unknown"


def _detail_lines(path: str, patch: str) -> tuple[str, list[str]] | None:
    """Return (kind, lines) for files whose permission/tool-relevant lines deserve a diff view."""
    changed = _changed_lines(patch)
    if _matches(path, "hooks/**", "**/.mcp.json", "**/*mcp*.json"):
        return "full patch", patch.splitlines()
    if _matches(path, ".github/workflows/**"):
        return "workflow permissions and actions", [ln for ln in changed if any(t in ln for t in WORKFLOW_TOKENS)]
    if _matches(path, "**/settings*.json"):
        return "permissions, hooks and env", [ln for ln in changed if any(t in ln for t in SETTINGS_TOKENS)]
    if _matches(path, "agents/**", "**/.claude/agents/**"):
        keys = [ln for ln in changed if AGENT_KEYS_RE.match(ln)]
        return "agent frontmatter", [*keys, f"# {len(changed) - len(keys)} other changed line(s) (prompt body)"]
    if _matches(path, "commands/**", "**/.claude/commands/**"):
        return "command frontmatter", [ln for ln in changed if COMMAND_KEYS_RE.match(ln)]
    return None


def _details_block(path: str, previous: str | None, patch: str | None) -> str | None:
    if patch is None:
        return None
    detail = _detail_lines(path, patch)
    if detail is None:
        return None
    kind, lines = detail
    note = ""
    if len(lines) > MAX_PATCH_LINES:
        note = f"\n(truncated: {len(lines) - MAX_PATCH_LINES} more line(s); review locally)"
        lines = lines[:MAX_PATCH_LINES]
    body = "\n".join(_clip(ln) for ln in lines) if lines else "(no lines of this kind changed)"
    fence = _fence_for(body)
    label = html.escape(_visible(path).replace("`", "'"), quote=True)
    if previous:
        label += " (was " + html.escape(_visible(previous).replace("`", "'"), quote=True) + ")"
    return (
        f"<details><summary><code>{label}</code> - {kind}</summary>\n\n"
        f"{fence}diff\n{body}\n{fence}{note}\n\n</details>\n"
    )


def build_report(files: list[dict[str, Any]], repo: str) -> tuple[bool, int, str]:
    """Return (sensitive, count, markdown). Markdown is empty when nothing is sensitive."""
    sensitive: list[dict[str, Any]] = []
    for entry in files:
        previous = entry.get("previous_filename")
        previous_s = previous if isinstance(previous, str) else None
        if is_sensitive(entry["filename"]) or (previous_s is not None and is_sensitive(previous_s)):
            sensitive.append(entry)
    if not sensitive:
        return False, 0, ""

    warnings: list[str] = []
    if len(files) >= API_FILE_LIMIT:
        warnings.append(
            f"The GitHub API returns at most {API_FILE_LIMIT} files per pull request; "
            "this list may be incomplete. Review the full diff locally."
        )
    rows: list[str] = []
    details: list[str] = []
    prompts: list[str] = []
    for entry in sensitive:
        name = entry["filename"]
        previous = entry.get("previous_filename") if isinstance(entry.get("previous_filename"), str) else None
        patch = entry.get("patch") if isinstance(entry.get("patch"), str) else None
        added, removed = _count(patch) if patch is not None else (0, 0)
        added = _int(entry.get("additions"), added)
        removed = _int(entry.get("deletions"), removed)
        cell = _code_span(name)
        if previous and previous != name:
            cell = f"{_code_span(previous)} -> {cell}"
        rows.append(f"| {cell} | {_status(entry.get('status'))} | +{added}/-{removed} |")
        if patch is None:
            warnings.append(f"{_code_span(name)}: patch not available (binary or too large); review locally.")
            continue
        hidden = hidden_codepoints("\n".join(ln for ln in patch.splitlines() if ln.startswith("+")))
        if hidden:
            warnings.append(
                f"{_code_span(name)}: added lines contain hidden or bidirectional Unicode "
                f"({', '.join(hidden)}). This can hide instructions from reviewers."
            )
        if hidden_codepoints(name):
            warnings.append(f"{_code_span(name)}: the file name contains hidden or bidirectional Unicode.")
        block = _details_block(name, previous, patch)
        if block is not None:
            details.append(block)
        elif _matches(name, "orchestrator/**", "**/CLAUDE.md", "**/AGENTS.md", "templates/CLAUDE.md.example"):
            prompts.append(f"- {_code_span(name)}: +{added}/-{removed}")

    link = f"https://github.com/{repo}/blob/main/CONTRIBUTING.md#security-sensitive-changes"
    head = [
        MARKER,
        "### Security-sensitive changes",
        "",
        f"This pull request touches {len(sensitive)} security-sensitive file(s) (hooks, permissions, agent "
        "tools, prompts, installer or CI). Code owner review is required. "
        f"See [Security-sensitive changes]({link}). This comment is generated automatically from the "
        "file list and does not replace a careful review.",
        "",
    ]
    for warning in warnings[:MAX_WARNINGS]:
        head.append(f"**Warning:** {warning}")
        head.append("")
    if len(warnings) > MAX_WARNINGS:
        head.append(f"**Warning:** {len(warnings) - MAX_WARNINGS} more warning(s) omitted.")
        head.append("")
    head += ["| File | Status | +/- |", "|---|---|---|", *rows[:MAX_TABLE_ROWS]]
    if len(rows) > MAX_TABLE_ROWS:
        head.append(f"| ... {len(rows) - MAX_TABLE_ROWS} more file(s) | | |")
    head.append("")
    if prompts:
        head += ["#### Prompt and policy changes (counts only)", "", *prompts, ""]

    parts = ["\n".join(head)]
    used = len(parts[0])
    omitted = 0
    if details:
        parts.append("#### Permission / tool changes\n")
        used += len(parts[-1])
        for block in details:
            if used + len(block) + 1 > COMMENT_LIMIT - 300:
                omitted += 1
                continue
            parts.append(block)
            used += len(block) + 1
    if omitted:
        parts.append(f"{omitted} detail section(s) omitted because of the comment size limit; review locally.\n")
    text = "\n".join(parts)
    if len(text) > COMMENT_LIMIT:  # defensive: the budget above should make this unreachable
        text = text[: COMMENT_LIMIT - 60].rstrip() + "\n\n(comment truncated; review locally)\n"
    return True, len(sensitive), text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify pull request files and render a review comment.")
    parser.add_argument("files", help="JSON / JSON-lines dump of the pull request files")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name used for links (default: %(default)s)")
    parser.add_argument("--out", help="write the Markdown comment here (default: stdout when sensitive)")
    parser.add_argument("--github-output", help="append sensitive=... and count=... to this file")
    args = parser.parse_args(argv)

    if not REPO_RE.fullmatch(args.repo):
        print(f"error: invalid --repo {args.repo!r}", file=sys.stderr)
        return 1
    try:
        with open(args.files, encoding="utf-8") as handle:
            files = parse_files(handle.read())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"error: cannot read {args.files}: {exc}", file=sys.stderr)
        return 1

    sensitive, count, comment = build_report(files, args.repo)
    if sensitive:
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(comment)
        else:
            sys.stdout.write(comment)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write(f"sensitive={'true' if sensitive else 'false'}\ncount={count}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
