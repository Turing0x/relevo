#!/usr/bin/env python3
"""Check that every agent has its documentation and that nothing is documented twice.

For each ``agents/<N>.md``: frontmatter ``name`` equals ``N``; ``docs/agents/<N>.md`` exists;
``docs/contracts/<n lowercase>-output.schema.json`` exists; ``docs/INDEX.md`` links the card.
Conversely, a card in ``docs/agents/`` without an agent is an error.

    check_agent_docs.py [--root DIR]
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK_TARGET = re.compile(r"\]\(\s*<?([^\s)>]+)")


def frontmatter_name(text: str) -> str | None:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() == "name":
            return value.strip().strip("'\"")
    return None


def names_in(directory: Path) -> set[str]:
    """Exact-case file names (the filesystem may be case-insensitive)."""
    return {p.name for p in directory.iterdir()} if directory.is_dir() else set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check agent documentation")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args(argv).root.resolve()

    agents = sorted((root / "agents").glob("*.md"))
    cards = names_in(root / "docs" / "agents")
    contracts = names_in(root / "docs" / "contracts")
    index = root / "docs" / "INDEX.md"
    linked: set[str] = set()
    if index.is_file():
        for target in LINK_TARGET.findall(index.read_bytes().decode("utf-8", errors="replace")):
            path = unquote(target.split("#", 1)[0])
            linked.add(posixpath.normpath(path))

    problems: list[str] = []
    if not agents:
        problems.append("agents/: no agent definitions found")
    if not index.is_file():
        problems.append("docs/INDEX.md: missing")
    for path in agents:
        stem = path.stem
        name = frontmatter_name(path.read_bytes().decode("utf-8", errors="replace"))
        if name != stem:
            problems.append(f"agents/{path.name}: frontmatter name is {name!r}, expected {stem!r}")
        if f"{stem}.md" not in cards:
            problems.append(f"agents/{path.name}: missing card docs/agents/{stem}.md")
        contract = f"{stem.lower()}-output.schema.json"
        if contract not in contracts:
            problems.append(f"agents/{path.name}: missing contract docs/contracts/{contract}")
        if f"agents/{stem}.md" not in linked:
            problems.append(f"agents/{path.name}: docs/INDEX.md does not link agents/{stem}.md")
    agent_names = {p.name for p in agents}
    for card in sorted(cards):
        if card.endswith(".md") and card not in agent_names:
            problems.append(f"docs/agents/{card}: card without an agent in agents/")

    if problems:
        print("Agent documentation problems:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"check_agent_docs: OK ({len(agents)} agents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
