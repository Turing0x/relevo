"""Cross-file consistency: what the docs, workflows and scripts say about each other must be true.

Pure regular expressions over repository files (standard library only), so it runs everywhere.
"""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
README_FILES = [ROOT / "README.md", ROOT / "README.es.md"]
DOC_FILES = [*README_FILES, ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", ROOT / "GOVERNANCE.md"]


# A line that documents installer flags (prose such as "git reset --hard" must not be mistaken for one).
INSTALLER_LINE_MARKERS = ("install.sh", "installer flags", "del instalador", "Desinstalar:", "Uninstall:")


def read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def makefile_targets() -> set[str]:
    return set(re.findall(r"(?m)^([a-z][a-z-]*):(?!=)", read("Makefile")))


def setup_labels() -> set[str]:
    block = re.search(r'(?ms)^LABELS="(.*?)"$', read("scripts", "setup-github.sh"))
    assert block is not None, "LABELS block not found in setup-github.sh"
    return {line.split("|")[0] for line in block.group(1).splitlines() if line.strip()}


def installer_flags() -> set[str]:
    return set(re.findall(r'add_argument\("(--[a-z-]+)"', read("scripts", "relevo_install.py")))


def slug(heading: str) -> str:
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    return {slug(m.group(1)) for m in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", path.read_text(encoding="utf-8"))}


class LabelsTests(unittest.TestCase):
    def test_labels_used_are_created_by_setup_script(self) -> None:
        known = setup_labels()
        used: dict[str, str] = {}
        for form in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")):
            m = re.search(r"(?m)^labels:\s*\[(.*?)\]\s*$", form.read_text(encoding="utf-8"))
            for label in m.group(1).split(",") if m else []:
                used[label.strip().strip("'\"")] = form.name
        dependabot = read(".github", "dependabot.yml")
        for block in re.finditer(r"(?m)^    labels:\n((?:      - .+\n)+)", dependabot):
            for label in re.findall(r"- (.+)", block.group(1)):
                used[label.strip().strip("'\"")] = "dependabot.yml"
        for path in WORKFLOWS:
            for label in re.findall(r"labels\[\]=([\w-]+)", path.read_text(encoding="utf-8")):
                used[label] = path.name
        self.assertTrue(used, "no label usage found: the regexes are stale")
        for label, where in used.items():
            with self.subTest(label=label, where=where):
                self.assertIn(label, known)

    def test_the_eight_requested_labels_exist(self) -> None:
        wanted = {
            "bug",
            "enhancement",
            "docs",
            "good first issue",
            "help wanted",
            "security-sensitive",
            "new-agent",
            "question",
        }
        self.assertTrue(wanted <= setup_labels())


class MakeTargetTests(unittest.TestCase):
    def test_make_targets_cited_in_docs_and_workflows_exist(self) -> None:
        targets = makefile_targets()
        self.assertTrue({"check", "lint", "test", "docs-check", "typecheck", "lint-workflows"} <= targets)
        cited: dict[str, str] = {}
        for path in [*DOC_FILES, ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md", *WORKFLOWS]:
            for m in re.finditer(
                r"(?m)(?:`|run:\s+|^\s*(?:\$ )?)make ([a-z][a-z-]*)\b", path.read_text(encoding="utf-8")
            ):
                cited[m.group(1)] = path.name
        self.assertTrue(cited)
        for target, where in cited.items():
            with self.subTest(target=target, where=where):
                self.assertIn(target, targets)

    def test_check_runs_every_documented_gate(self) -> None:
        m = re.search(r"(?m)^check:\s*(.+?)(?:\s+##.*)?$", read("Makefile"))
        assert m is not None
        self.assertEqual(set(m.group(1).split()), {"lint", "lint-workflows", "typecheck", "test", "docs-check"})


class VersionTests(unittest.TestCase):
    def test_installer_version_matches_first_changelog_release(self) -> None:
        m = re.search(r'(?m)^VERSION = "([^"]+)"', read("scripts", "relevo_install.py"))
        assert m is not None
        releases = re.findall(r"(?m)^## \[(\d+\.\d+\.\d+)\]", read("CHANGELOG.md"))
        self.assertTrue(releases)
        self.assertEqual(m.group(1), releases[0])

    def test_readmes_state_the_same_version(self) -> None:
        m = re.search(r'(?m)^VERSION = "([^"]+)"', read("scripts", "relevo_install.py"))
        assert m is not None
        for path in README_FILES:
            with self.subTest(file=path.name):
                self.assertIn(f"`{m.group(1)}`", path.read_text(encoding="utf-8"))


class AnchorTests(unittest.TestCase):
    def test_anchors_promised_by_the_plan_exist(self) -> None:
        contributing = anchors(ROOT / "CONTRIBUTING.md")
        security = anchors(ROOT / "SECURITY.md")
        self.assertIn("security-sensitive-changes", contributing)
        self.assertIn("developer-certificate-of-origin-dco", contributing)
        self.assertIn("reporting-a-vulnerability", security)
        self.assertIn("ai-orchestrator-specific-risks", security)

    def test_anchors_used_by_automation_exist(self) -> None:
        # The sensitive-paths comment links into these headings.
        text = read("scripts", "sensitive_diff.py") + read(".github", "PULL_REQUEST_TEMPLATE.md")
        for filename, fragment in re.findall(r"(CONTRIBUTING\.md|SECURITY\.md)#([\w-]+)", text):
            with self.subTest(target=f"{filename}#{fragment}"):
                self.assertIn(fragment, anchors(ROOT / filename))


class ReadmeTests(unittest.TestCase):
    def test_readmes_link_the_docs_index(self) -> None:
        for path in README_FILES:
            with self.subTest(file=path.name):
                self.assertIn("docs/INDEX.md", path.read_text(encoding="utf-8"))

    def test_installer_flags_cited_exist_in_argparse(self) -> None:
        flags = installer_flags()
        self.assertTrue({"--dry-run", "--force", "--prefix", "--no-settings", "--no-claude-md"} <= flags)
        for path in DOC_FILES:
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if not any(marker in line for marker in INSTALLER_LINE_MARKERS):
                    continue
                for flag in re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", line):
                    if flag in {"--apply", "--help", "--version"}:
                        continue
                    with self.subTest(file=path.name, flag=flag):
                        self.assertIn(flag, flags)

    def test_readmes_cite_the_real_settings_template_counts(self) -> None:
        template = json.loads(read("templates", "settings.example.json"))
        ask = len(template["permissions"]["ask"])
        deny = len(template["permissions"]["deny"])
        for path in README_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertIn(f"{ask} ", text)
                self.assertRegex(text, rf"\b{ask}\b")
                self.assertRegex(text, rf"\b{deny}\b")

    def test_readmes_cite_files_that_exist(self) -> None:
        for path in README_FILES:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(((?!https?:|#|mailto:)[^)#\s]+)", text):
                with self.subTest(file=path.name, target=target):
                    self.assertTrue((ROOT / target).exists())


class InstallerTextTests(unittest.TestCase):
    def test_markers_match_between_installer_template_and_docs(self) -> None:
        src = read("scripts", "relevo_install.py")
        begin = re.search(r'(?m)^BEGIN_MARK = "(.+)"', src)
        end = re.search(r'(?m)^END_MARK = "(.+)"', src)
        assert begin is not None and end is not None
        self.assertEqual(begin.group(1), "<!-- relevo:begin -->")
        self.assertEqual(end.group(1), "<!-- relevo:end -->")
        for path in README_FILES:
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(begin.group(1), text)
                self.assertIn(end.group(1), text)

    def test_manifest_and_backup_paths_match_the_docs(self) -> None:
        src = read("scripts", "relevo_install.py")
        self.assertIn('MANIFEST_REL = "orchestrator/.relevo-manifest.json"', src)
        self.assertIn('BACKUP_DIRNAME = ".relevo-backups"', src)
        for path in README_FILES:
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("orchestrator/.relevo-manifest.json", text)
                self.assertIn(".relevo-backups/", text)

    def test_sensitive_paths_comment_marker_matches_workflow(self) -> None:
        marker = "<!-- relevo:sensitive-paths -->"
        self.assertIn(marker, read("scripts", "sensitive_diff.py"))
        self.assertIn(marker, read(".github", "workflows", "sensitive-paths.yml"))


def schema(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(read("docs", "contracts", name))
    return data


def output_block(agent: str) -> list[str]:
    lines = read("agents", f"{agent}.md").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Salida final"))
    return lines[start + 1 :]


def high_risk_items(text: str, item: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip().rstrip(".").lower() for m in re.finditer(item, text)}


class RiskLineTests(unittest.TestCase):
    """`Riesgo: <N>[,<N>] (<motivo>) | ninguno` in implementador and rapido (policy §6bis)."""

    WORKERS = ("implementador", "rapido")
    VALID = ("ninguno", "3 (toca código compartido)", "2,5 (guard-secrets e instalador)", "6 (sin test de regresión)")
    INVALID = (
        "",
        "bajo",
        "alto",
        "Ninguno",
        "ninguna",
        "3",
        "7 (x)",
        "0 (x)",
        "3,(x)",
        "3, 5 (x)",
        "3 ()",
        "Riesgo: 3 (x)",
    )

    def pattern(self, agent: str) -> re.Pattern[str]:
        contract = schema(f"{agent}-output.schema.json")
        self.assertIn("riesgo", contract["required"])
        return re.compile(contract["properties"]["riesgo"]["pattern"])

    def test_both_workers_share_the_same_risk_pattern(self) -> None:
        self.assertEqual(self.pattern("implementador").pattern, self.pattern("rapido").pattern)

    def test_valid_risk_values_match(self) -> None:
        for agent in self.WORKERS:
            pattern = self.pattern(agent)
            examples = schema(f"{agent}-output.schema.json")["properties"]["riesgo"]["examples"]
            for value in (*self.VALID, *examples):
                with self.subTest(agent=agent, value=value):
                    self.assertRegex(value, pattern)

    def test_invalid_risk_values_do_not_match(self) -> None:
        for agent in self.WORKERS:
            pattern = self.pattern(agent)
            for value in self.INVALID:
                with self.subTest(agent=agent, value=value):
                    self.assertIsNone(pattern.fullmatch(value))

    def test_agents_print_the_risk_line_within_eight_lines(self) -> None:
        for agent in self.WORKERS:
            block = output_block(agent)
            with self.subTest(agent=agent):
                self.assertIn("Riesgo: <N>[,<N>] (<motivo>) | ninguno", block)
                self.assertLessEqual(len(block), 8)
                self.assertIn(
                    "código compartido usado por comportamiento no pedido (= 3)", read("agents", f"{agent}.md")
                )

    def test_policy_feeds_the_risk_line_into_final_risk(self) -> None:
        policy = read("orchestrator", "policy.md")
        self.assertRegex(policy, r"riesgo final = max\([^)]*línea `Riesgo:` del worker")
        self.assertIn("Sigue solo tu brief, §4, §6 y §6bis.", policy)


class PolicySyncTests(unittest.TestCase):
    """Copies the clasificador keeps of policy.md (it runs with omitClaudeMd)."""

    def test_high_risk_list_has_the_same_numbers_and_text(self) -> None:
        policy = read("orchestrator", "policy.md")
        section = policy.split("## 6bis.", 1)[1].split("\n## ", 1)[0]
        in_policy = high_risk_items(section, r"(?m)^([1-9])\. (.+)$")
        in_clasificador = high_risk_items(read("agents", "clasificador.md"), r"(?m)^  ([1-9]) (.+)$")
        self.assertEqual(sorted(in_policy), [str(n) for n in range(1, 7)])
        self.assertEqual(in_policy, in_clasificador)

    def test_busqueda_row_is_synchronised(self) -> None:
        row = re.search(r"(?m)^\| busqueda \| (.+?) \| (.+?) \|$", read("orchestrator", "policy.md"))
        assert row is not None
        line = next(x for x in read("agents", "clasificador.md").splitlines() if x.strip().startswith("busqueda →"))
        self.assertIn(f"en_linea si {row.group(1)};", line)
        for text in ("1 lote de ≤3 llamadas (~10k tokens)", ">5 búsquedas secuenciales"):
            with self.subTest(text=text):
                self.assertIn(text, row.group(0))
                self.assertIn(text, line)


class BriefAndVerifierContractTests(unittest.TestCase):
    def test_allowed_surface_rejects_broad_or_absolute_paths(self) -> None:
        items = schema("brief.schema.json")["properties"]["superficie_permitida"]["items"]
        pattern = re.compile(str(items["pattern"]))
        banned = set(items["not"]["enum"])
        for value in ("src/validators/user.js", "test/auth/*.test.js", "docs/**/*.md", ".github/workflows/ci.yml"):
            with self.subTest(value=value):
                self.assertRegex(value, pattern)
                self.assertNotIn(value, banned)
        for value in ("/etc/passwd", "~/x", "C:/x", "\\x", "../x", "a/../b", "a/.."):
            with self.subTest(value=value):
                self.assertIsNone(pattern.fullmatch(value))
        self.assertTrue({".", "./", "**"} <= banned)

    def test_brief_carries_base_commit_and_recheck_findings(self) -> None:
        brief = schema("brief.schema.json")
        self.assertNotIn("archivos_permitidos", brief["properties"])
        for field in ("base_commit", "modo", "recheck_findings"):
            with self.subTest(field=field):
                self.assertIn(field, brief["properties"])
        self.assertRegex("37a2984", brief["properties"]["base_commit"]["pattern"])
        self.assertIn("recheck_findings", json.dumps(brief["allOf"]))

    def test_verifier_findings_are_blocking_or_warning(self) -> None:
        props = schema("verificador-output.schema.json")["properties"]
        pattern = re.compile(str(props["hallazgos"]["items"]["pattern"]))
        for value in ("ninguno", "[bloqueante] a.py:3 — x — y", "[advertencia] a.py:3 — x — y"):
            with self.subTest(value=value):
                self.assertRegex(value, pattern)
        for value in ("[alta] a.py:3 — x — y", "[estilo] a.py:1 — x — y", ""):
            with self.subTest(value=value):
                self.assertIsNone(pattern.fullmatch(value))
        self.assertIn("recheck", props)

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "jsonschema not installed")
    def test_sample_reports_validate_against_the_schemas(self) -> None:
        import jsonschema

        ok = {"estado": "OK", "archivos": ["a.py"], "verificacion": "make test → OK", "pendientes": "ninguno"}
        validate = jsonschema.validate
        validate({**ok, "riesgo": "3 (contrato de salida)"}, schema("implementador-output.schema.json"))
        validate({"estado": "OK", "riesgo": "ninguno"}, schema("rapido-output.schema.json"))
        for bad in (ok, {**ok, "riesgo": "bajo"}):
            with self.subTest(report=bad), self.assertRaises(jsonschema.ValidationError):
                validate(bad, schema("implementador-output.schema.json"))
        brief = schema("brief.schema.json")
        validate({"objetivo": "x", "superficie_permitida": ["src/a.py"], "modo": "normal"}, brief)
        for bad_brief in (
            {"objetivo": "x", "superficie_permitida": ["."]},
            {"objetivo": "x", "superficie_permitida": ["/abs/a.py"]},
            {"objetivo": "x", "modo": "recheck", "base_commit": "37a2984"},
            {"objetivo": "x", "modo": "recheck", "base_commit": "37a2984", "recheck_findings": []},
        ):
            with self.subTest(brief=bad_brief), self.assertRaises(jsonschema.ValidationError):
                validate(bad_brief, brief)


if __name__ == "__main__":
    unittest.main()
