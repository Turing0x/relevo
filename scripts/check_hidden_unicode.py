#!/usr/bin/env python3
"""Fail if any text file contains invisible or bidirectional-control Unicode characters.

These characters can hide instructions inside prompts, agent definitions and scripts.
Reports ``file:line:col U+XXXX``.

    check_hidden_unicode.py [--root DIR]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

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
# Inclusive code point ranges: soft hyphen, zero-width and direction marks, bidi embeddings and
# isolates, word joiner and invisible operators, BOM / zero-width no-break space, tag characters.
RANGES = (
    (0x00AD, 0x00AD),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x2064),
    (0x2066, 0x2069),
    (0xFEFF, 0xFEFF),
    (0xE0000, 0xE007F),
)


def is_hidden(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in RANGES)


def scan_text(text: str) -> list[tuple[int, int, int]]:
    """Return ``(line, column, code point)`` for every hidden character (1-based)."""
    hits: list[tuple[int, int, int]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        hits.extend((lineno, col, ord(ch)) for col, ch in enumerate(line, start=1) if is_hidden(ch))
    return hits


def text_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_file() and not path.is_symlink():
                found.append(path)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect hidden Unicode characters")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args(argv).root.resolve()
    problems: list[str] = []
    scanned = 0
    for path in text_files(root):
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue  # binary
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        rel = path.relative_to(root).as_posix()
        problems.extend(f"{rel}:{line}:{col} U+{code:04X}" for line, col, code in scan_text(text))
    if problems:
        print("Hidden Unicode characters found:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"check_hidden_unicode: OK ({scanned} text files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
