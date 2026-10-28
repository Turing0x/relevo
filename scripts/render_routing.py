#!/usr/bin/env python3
"""Render table B of the policy from ``orchestrator/routing.json``.

The JSON is the single source of the routing rows and their thresholds. This script rewrites
the text between ``<!-- relevo:routing:begin -->`` and ``<!-- relevo:routing:end -->`` in
``orchestrator/policy.md`` (Markdown table, §2B) and in ``agents/clasificador.md`` (the copy the
clasificador reads, since it runs with ``omitClaudeMd``). With ``--check`` nothing is written and
the exit code is 1 if either copy differs from what the JSON renders.

    render_routing.py [--check] [--root DIR]
"""

from __future__ import annotations

import argparse
import difflib
import json
import string
import sys
from pathlib import Path
from typing import Any

BEGIN = "<!-- relevo:routing:begin -->"
END = "<!-- relevo:routing:end -->"
SOURCE = "orchestrator/routing.json"
POLICY = "orchestrator/policy.md"
CLASIFICADOR = "agents/clasificador.md"
TYPES = ("busqueda", "mecanica", "implementacion", "arquitectura", "bug_dificil", "revision")
ROW_KEYS = ("tipos", "etiqueta", "en_linea", "si_no", "clasificador")
CLASIFICADOR_INDENT = "  "


class RoutingError(Exception):
    """The JSON or a target file is not usable. The message is printed and the exit code is 2."""


def placeholders(template: str | None) -> set[str]:
    if template is None:
        return set()
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def load(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / SOURCE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RoutingError(f"cannot read {SOURCE}: {exc}") from exc
    validate(data)
    result: dict[str, Any] = data
    return result


def validate(data: Any) -> None:
    """Every type covered once, every threshold a positive integer used by both copies of its row."""
    if not isinstance(data, dict):
        raise RoutingError(f"{SOURCE}: top-level value must be an object")
    thresholds = data.get("umbrales")
    rows = data.get("filas")
    if not isinstance(thresholds, dict) or not isinstance(rows, list) or not rows:
        raise RoutingError(f'{SOURCE}: "umbrales" must be an object and "filas" a non-empty array')
    for name, value in thresholds.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RoutingError(f"{SOURCE}: umbral {name} must be a positive integer")
    seen: list[str] = []
    used: set[str] = set()
    for index, row in enumerate(rows):
        where = f"{SOURCE}: filas[{index}]"
        if not isinstance(row, dict) or set(row) != set(ROW_KEYS):
            raise RoutingError(f"{where} must have exactly the keys {', '.join(ROW_KEYS)}")
        if not isinstance(row["tipos"], list) or not row["tipos"]:
            raise RoutingError(f'{where}: "tipos" must be a non-empty array')
        seen += row["tipos"]
        for key in ("etiqueta", "si_no", "clasificador"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise RoutingError(f'{where}: "{key}" must be a non-empty string')
        if row["en_linea"] is not None and (not isinstance(row["en_linea"], str) or not row["en_linea"].strip()):
            raise RoutingError(f'{where}: "en_linea" must be null or a non-empty string')
        if any("|" in cell or "\n" in cell for cell in (row["etiqueta"], row["si_no"], row["en_linea"] or "")):
            raise RoutingError(f"{where}: table cells cannot contain '|' or newlines")
        if "\n" in row["clasificador"]:
            raise RoutingError(f'{where}: "clasificador" must be a single line')
        in_table = placeholders(row["en_linea"]) | placeholders(row["si_no"]) | placeholders(row["etiqueta"])
        in_copy = placeholders(row["clasificador"])
        unknown = (in_table | in_copy) - set(thresholds)
        if unknown:
            raise RoutingError(f"{where}: unknown umbral {', '.join(sorted(unknown))}")
        if in_table != in_copy:
            diff = sorted(in_table ^ in_copy)
            raise RoutingError(f"{where}: umbral {', '.join(diff)} must appear in both the table and the copy")
        used |= in_table
    if sorted(seen) != sorted(TYPES):
        raise RoutingError(f"{SOURCE}: filas must cover each of {', '.join(TYPES)} exactly once")
    unused = set(thresholds) - used
    if unused:
        raise RoutingError(f"{SOURCE}: umbral {', '.join(sorted(unused))} is not used by any row")


def render_policy(data: dict[str, Any]) -> str:
    values = data["umbrales"]
    lines = ["| Tipo | En línea si… | Si no |", "|---|---|---|"]
    for row in data["filas"]:
        inline = row["en_linea"].format(**values) if row["en_linea"] else "—"
        lines.append(f"| {row['etiqueta'].format(**values)} | {inline} | {row['si_no'].format(**values)} |")
    return "\n".join(lines)


def render_clasificador(data: dict[str, Any]) -> str:
    values = data["umbrales"]
    return "\n".join(CLASIFICADOR_INDENT + row["clasificador"].format(**values) for row in data["filas"])


def replace_block(text: str, body: str, name: str) -> str:
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise RoutingError(f"{name}: expected exactly one {BEGIN} and one {END}")
    start = text.index(BEGIN) + len(BEGIN)
    end = text.index(END)
    if end < start:
        raise RoutingError(f"{name}: {END} comes before {BEGIN}")
    return text[:start] + "\n" + body + "\n" + text[end:]


def extract_block(text: str, name: str) -> str:
    """The text between the markers, without the surrounding newlines."""
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise RoutingError(f"{name}: expected exactly one {BEGIN} and one {END}")
    return text.split(BEGIN, 1)[1].split(END, 1)[0].strip("\n")


def targets(data: dict[str, Any]) -> dict[str, str]:
    return {POLICY: render_policy(data), CLASIFICADOR: render_clasificador(data)}


def run(root: Path, check: bool) -> int:
    data = load(root)
    stale = 0
    for rel, body in targets(data).items():
        path = root / rel
        try:
            old = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RoutingError(f"cannot read {rel}: {exc}") from exc
        new = replace_block(old, body, rel)
        if new == old:
            continue
        if check:
            stale += 1
            diff = difflib.unified_diff(
                old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{rel}", f"b/{rel}"
            )
            sys.stdout.writelines(diff)
            print(f"{rel}: table B is out of sync with {SOURCE}", file=sys.stderr)
        else:
            path.write_text(new, encoding="utf-8")
            print(f"rendered {rel}")
    if stale:
        print("run: python3 scripts/render_routing.py", file=sys.stderr)
        return 1
    if check:
        print(f"routing: {POLICY} and {CLASIFICADOR} match {SOURCE}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if a copy is out of sync")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="repository root")
    args = parser.parse_args(argv)
    try:
        return run(Path(args.root), args.check)
    except RoutingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
