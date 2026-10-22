"""Tests for scripts/check_*.py, using small fixture trees in a temporary directory."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
# Built with chr() so that this file itself contains no hidden characters.
ZWSP = chr(0x200B)
BOM = chr(0xFEFF)
RLO = chr(0x202E)


def have_jsonschema() -> bool:
    try:
        importlib.import_module("jsonschema")
    except ImportError:
        return False
    return True


class CheckCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "repo"
        self.root.mkdir()

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def run_script(self, name: str, root: Path | None = None, ci: bool = False) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k != "CI"}
        env["HOME"] = str(self.tmp)
        if ci:
            env["CI"] = "true"
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name), "--root", str(root or self.root)],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )


class CheckLinksTests(CheckCase):
    def test_valid_links_pass(self) -> None:
        self.write("README.md", "[doc](docs/a.md) [sec](docs/a.md#second-part) [self](#top)\n\n# Top\n")
        self.write("docs/a.md", "# A\n\n## Second part\n\n[back](../README.md#top) [root](/README.md)\n")
        self.write("docs/img.png", "x")
        self.write("docs/b.md", '![img](img.png) [t](<a.md> "title") [web](https://example.com/x) [m](mailto:a@b.c)\n')
        result = self.run_script("check_links.py")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_broken_file_link_fails(self) -> None:
        self.write("README.md", "[gone](docs/missing.md)\n")
        result = self.run_script("check_links.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.md: docs/missing.md", result.stderr)

    def test_broken_anchor_fails(self) -> None:
        self.write("README.md", "[x](docs/a.md#nope)\n")
        self.write("docs/a.md", "# Real heading\n")
        result = self.run_script("check_links.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/a.md#nope", result.stderr)

    def test_accented_anchor_and_duplicate_headings(self) -> None:
        self.write(
            "README.md",
            "[a](docs/a.md#paso-4-verificación-dos-gates) [b](docs/a.md#repeat) [c](docs/a.md#repeat-1)\n",
        )
        self.write("docs/a.md", "## Paso 4: Verificación (dos gates)\n\n## Repeat\n\n## Repeat\n")
        result = self.run_script("check_links.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("README.md", "[d](docs/a.md#repeat-2)\n")
        self.assertEqual(self.run_script("check_links.py").returncode, 1)

    def test_code_is_ignored(self) -> None:
        text = "```\n[x](nope.md)\n```\n\nInline `[y](nope2.md)` code.\n\n<!-- [z](nope3.md) -->\n"
        self.write("README.md", text)
        self.assertEqual(self.run_script("check_links.py").returncode, 0)

    def test_line_anchors_and_query_are_ignored(self) -> None:
        self.write("README.md", "[l](docs/a.md#L10) [r](docs/a.md#L3-L9) [q](docs/a.md?plain=1)\n")
        self.write("docs/a.md", "# A\n")
        self.assertEqual(self.run_script("check_links.py").returncode, 0)

    def test_reference_definition_is_checked(self) -> None:
        self.write("README.md", "[ref]: docs/missing.md\n")
        self.assertEqual(self.run_script("check_links.py").returncode, 1)

    def test_excluded_directories_are_skipped(self) -> None:
        self.write(".claude/work/plan.md", "[x](nope.md)\n")
        self.write(".github/PULL_REQUEST_TEMPLATE.md", "[x](nope.md)\n")
        result = self.run_script("check_links.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn(".github/PULL_REQUEST_TEMPLATE.md", result.stderr)
        self.assertNotIn(".claude", result.stderr)

    def test_real_repo_has_no_broken_links(self) -> None:
        result = self.run_script("check_links.py", root=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)


class CheckHiddenUnicodeTests(CheckCase):
    def test_clean_tree_passes(self) -> None:
        self.write("a.py", "print('plain áé text')\n")
        self.assertEqual(self.run_script("check_hidden_unicode.py").returncode, 0)

    def test_hidden_characters_are_reported_with_position(self) -> None:
        self.write("docs/a.md", "first line\nab" + ZWSP + "c\n")
        self.write("agents/x.md", BOM + "starts with a BOM\n")
        self.write("hooks/tool", "x" + RLO + "y\n")
        self.write("t.md", "tag " + chr(0xE0041) + " char\n")
        result = self.run_script("check_hidden_unicode.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/a.md:2:3 U+200B", result.stderr)
        self.assertIn("agents/x.md:1:1 U+FEFF", result.stderr)
        self.assertIn("hooks/tool:1:2 U+202E", result.stderr)
        self.assertIn("U+E0041", result.stderr)

    def test_binary_and_excluded_files_are_skipped(self) -> None:
        (self.root / "image.png").write_bytes(b"\x00\x01\xe2\x80\x8b")
        self.write(".git/config", "x" + ZWSP + "y\n")
        self.assertEqual(self.run_script("check_hidden_unicode.py").returncode, 0)


class CheckAgentDocsTests(CheckCase):
    def build_ok(self) -> None:
        self.write("agents/Foo.md", "---\nname: Foo\nmodel: haiku\n---\nbody\n")
        self.write("docs/agents/Foo.md", "# Foo\n")
        self.write("docs/contracts/foo-output.schema.json", "{}\n")
        self.write("docs/INDEX.md", "| [agents/Foo.md](agents/Foo.md) | card |\n")

    def test_complete_setup_passes(self) -> None:
        self.build_ok()
        result = self.run_script("check_agent_docs.py")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_card(self) -> None:
        self.build_ok()
        (self.root / "docs" / "agents" / "Foo.md").unlink()
        result = self.run_script("check_agent_docs.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing card", result.stderr)

    def test_missing_contract(self) -> None:
        self.build_ok()
        (self.root / "docs" / "contracts" / "foo-output.schema.json").unlink()
        result = self.run_script("check_agent_docs.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing contract", result.stderr)

    def test_not_linked_from_index(self) -> None:
        self.build_ok()
        self.write("docs/INDEX.md", "nothing here\n")
        result = self.run_script("check_agent_docs.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not link", result.stderr)

    def test_frontmatter_name_mismatch(self) -> None:
        self.build_ok()
        self.write("agents/Foo.md", "---\nname: Bar\n---\nbody\n")
        result = self.run_script("check_agent_docs.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("frontmatter name", result.stderr)

    def test_card_without_agent(self) -> None:
        self.build_ok()
        self.write("docs/agents/Orphan.md", "# Orphan\n")
        result = self.run_script("check_agent_docs.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("card without an agent", result.stderr)

    def test_real_repo_is_consistent(self) -> None:
        result = self.run_script("check_agent_docs.py", root=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)


class CheckSchemasTests(CheckCase):
    def schema(self, name: str, body: object) -> None:
        self.write(f"docs/contracts/{name}.json", json.dumps(body))

    def test_valid_schema(self) -> None:
        self.schema("a", {"$schema": DRAFT, "type": "object"})
        result = self.run_script("check_schemas.py")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_json_fails(self) -> None:
        self.write("docs/contracts/a.json", "{ nope")
        self.assertEqual(self.run_script("check_schemas.py").returncode, 1)

    def test_wrong_draft_fails(self) -> None:
        self.schema("a", {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"})
        result = self.run_script("check_schemas.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("2020-12", result.stderr)

    def test_empty_directory_fails(self) -> None:
        (self.root / "docs" / "contracts").mkdir(parents=True)
        self.assertEqual(self.run_script("check_schemas.py").returncode, 1)

    @unittest.skipUnless(have_jsonschema(), "jsonschema not installed")
    def test_metaschema_violation_fails(self) -> None:
        self.schema("a", {"$schema": DRAFT, "type": 5})
        result = self.run_script("check_schemas.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid schema", result.stderr)

    @unittest.skipIf(have_jsonschema(), "only meaningful without jsonschema")
    def test_missing_jsonschema_skips_locally_and_fails_in_ci(self) -> None:
        self.schema("a", {"$schema": DRAFT, "type": 5})
        local = self.run_script("check_schemas.py")
        self.assertEqual(local.returncode, 0)
        self.assertIn("SKIP", local.stdout)
        self.assertEqual(self.run_script("check_schemas.py", ci=True).returncode, 1)

    def test_real_repo_schemas(self) -> None:
        result = self.run_script("check_schemas.py", root=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
