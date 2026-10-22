#!/usr/bin/env python3
"""Validate the JSON Schemas in docs/contracts/.

Each file must be valid JSON, declare the 2020-12 draft in ``$schema`` and, when the
``jsonschema`` package is installed, pass its metaschema check. Without ``jsonschema`` the
metaschema part is skipped locally (exit 0) and fails when the ``CI`` variable is set.

    check_schemas.py [--root DIR]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

DRAFT = "https://json-schema.org/draft/2020-12/schema"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate docs/contracts/*.json")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args(argv).root.resolve()
    files = sorted((root / "docs" / "contracts").glob("*.json"))
    if not files:
        print("check_schemas: no schemas found in docs/contracts", file=sys.stderr)
        return 1

    problems: list[str] = []
    schemas: list[tuple[Path, Any]] = []
    for path in files:
        name = path.relative_to(root).as_posix()
        try:
            schema = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{name}: invalid JSON ({exc})")
            continue
        if not isinstance(schema, dict):
            problems.append(f"{name}: top-level value must be an object")
        elif schema.get("$schema") != DRAFT:
            problems.append(f"{name}: $schema must be {DRAFT}")
        else:
            schemas.append((path, schema))

    skipped = False
    try:
        jsonschema = importlib.import_module("jsonschema")
    except ImportError:
        jsonschema = None
    if jsonschema is None:
        if os.environ.get("CI"):
            problems.append("jsonschema is not installed (required when CI is set)")
        else:
            skipped = True
            print("SKIP: jsonschema not installed (run make install-dev); metaschema check not performed")
    else:
        for path, schema in schemas:
            try:
                jsonschema.validators.validator_for(schema).check_schema(schema)
            except Exception as exc:  # jsonschema.SchemaError and friends
                problems.append(f"{path.relative_to(root).as_posix()}: invalid schema ({exc})")

    if problems:
        print("Schema problems:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"check_schemas: OK ({len(files)} schemas{', metaschema skipped' if skipped else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
