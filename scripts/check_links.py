#!/usr/bin/env python3
"""Offline check of relative links and anchors in every Markdown file of the repo.

Checks inline links, images and reference definitions. External URLs are ignored (the
Docs workflow checks them separately). Anchors use GitHub-style slugs.

    check_links.py [--root DIR]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

EXCLUDED_DIRS = {
    ".git",
    ".claude",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".codeql-shadow",
}
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
LINE_ANCHOR = re.compile(r"^L\d+(-L\d+)?$")
INLINE_TARGET = re.compile(r"\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REF_DEF = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)")
HEADING = re.compile(r"^ {0,3}#{1,6}\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_ANCHOR = re.compile(r"""<a\s[^>]*?(?:name|id)=["']([^"']+)["']""", re.IGNORECASE)


def markdown_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        found.extend(Path(dirpath) / name for name in sorted(filenames) if name.endswith(".md"))
    return found


def visible_lines(text: str) -> list[str]:
    """Lines of ``text`` without HTML comments and fenced code blocks."""
    text = HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    lines: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        match = FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)[0]
            continue
        if fence is not None:
            if match and match.group(1)[0] == fence:
                fence = None
            continue
        lines.append(line)
    return lines


def slugify(heading: str) -> str:
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "").lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path in cache:
        return cache[path]
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    text = path.read_bytes().decode("utf-8", errors="replace")
    for line in visible_lines(text):
        match = HEADING.match(line)
        if match:
            slug = slugify(match.group(1))
            seen = counts.get(slug, 0)
            counts[slug] = seen + 1
            anchors.add(slug if seen == 0 else f"{slug}-{seen}")
        anchors.update(HTML_ANCHOR.findall(line))
    cache[path] = anchors
    return anchors


def targets_of(path: Path) -> list[str]:
    text = path.read_bytes().decode("utf-8", errors="replace")
    found: list[str] = []
    for line in visible_lines(text):
        line = CODE_SPAN.sub("", line)
        found.extend(INLINE_TARGET.findall(line))
        match = REF_DEF.match(line)
        if match:
            found.append(match.group(1))
    return [t[1:-1] if t.startswith("<") else t for t in found]


def check_link(root: Path, source: Path, link: str, cache: dict[Path, set[str]]) -> str | None:
    """Return a reason if ``link`` (found in ``source``) is broken, else None."""
    if SCHEME.match(link) or link.startswith("//"):
        return None
    path_part, _, fragment = link.partition("#")
    path_part = unquote(path_part.split("?", 1)[0])
    if not path_part:
        target = source
    elif path_part.startswith("/"):
        target = root / path_part.lstrip("/")
    else:
        target = source.parent / path_part
    if not os.path.exists(target):
        return "file not found"
    checks_anchor = fragment and not LINE_ANCHOR.match(fragment) and target.is_file() and target.suffix == ".md"
    if checks_anchor and unquote(fragment).lower() not in anchors_of(target, cache):
        return "anchor not found"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args(argv).root.resolve()
    cache: dict[Path, set[str]] = {}
    problems: list[str] = []
    files = markdown_files(root)
    for path in files:
        for link in targets_of(path):
            reason = check_link(root, path, link, cache)
            if reason:
                problems.append(f"{path.relative_to(root).as_posix()}: {link} ({reason})")
    if problems:
        print("Broken links:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"check_links: OK ({len(files)} Markdown files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
