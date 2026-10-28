# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Numbered high-risk list (policy §6bis), shared with `clasificador`, and a mandatory `Riesgo:` line in the `implementador` and `rapido` reports that feeds the final risk.
- `verificador` receives `base_commit`: a finding blocks only if the change caused it and it does not reproduce on the base; precision gate; `recheck` mode that reviews only the previous findings.
- Brief: `## Superficie permitida` section (never `.` or absolute paths), `base_commit`, `modo` and `recheck_findings[]`.
- Router check before the final summary: re-run 1 reported command and open 1 `Explore` citation.
- ADR 0009 and consistency tests for the risk line, the high-risk list and the `busqueda` row.
- `orchestrator/routing.json`, the single source of table B (rows and thresholds), and `scripts/render_routing.py`, which rewrites both copies (policy §2B and `clasificador`) between `relevo:routing` markers. `--check` runs in `make docs-check` and CI.
- Task logbook `.claude/work/<task>/estado.md` (policy §3) with the request, route, `arquitecto: N/1`, `ciclos: N/2`, slices, last verdict and next step; its counters win over the chat memory after a compaction and never go down.
- `orch-resume` hook (SessionStart, matchers `compact` and `resume`, 5 s timeout) that prints the open logbook of the current git root. It refuses when `.claude/work/` is not gitignored.
- Installer: `--pin-backup` and a `backups` command (`--pin`, `--unpin`) to list and pin backups.
- ADR 0010.

### Changed

- `busqueda` stays inline only if it also fits in 1 batch of ≤3 calls (~10k tokens); >5 sequential searches go to `Explore`.
- The 2nd cycle after a `RECHAZADO` for implementation is a recheck; a new finding is a warning and does not use a cycle.
- Parallel workers only for independent behaviour units (~100+ lines each, code + tests + docs together).
- Blocking prompts (`PENDIENTE_APROBACION`, `AMPLIAR`) are relayed with every option verbatim.
- Backups are deduplicated by checksum and only the 5 most recently used are kept, plus pinned ones and those holding an original replaced with `--force`.
- The `settings.json` merge fails without writing anything if the file has comments (JSONC) or duplicate keys.
- The hook merge may register one template command under several matchers; a command the user already has for that event is still left alone.

## [0.1.0] - 2026-10-22

First public release (alpha).

### Added

- Orchestration policy (`orchestrator/policy.md`): classification, routing tables, budget, two-gate verification and the list of sensitive actions that need human approval.
- Six workers: `clasificador`, `Explore` and `rapido` (haiku), `implementador` (sonnet), `arquitecto` and `verificador` (opus).
- Three hooks: `block-force-push` (blocks force pushes and remote branch deletions), `guard-secrets` (asks for confirmation before touching `.env`, private keys or credentials) and `orch-telemetry` (one local log line per finished worker).
- `orchestrator/stats.py` and the `/orch-stats` command to summarize the telemetry.
- `/orchestrator-init` command and `orchestrator/project-template.md` to enable the orchestrator per project.
- Technical documentation in `docs/` (in Spanish): architecture, routing, failure modes, glossary, agent data sheets, JSON Schemas for the worker contracts, decision records and examples.
- Installer and uninstaller (`scripts/install.sh`, `scripts/uninstall.sh`) with `--dry-run`, backups and a manifest, and templates for `settings.json` and `CLAUDE.md`.
- Test suite, linting, type checks and documentation checks, runnable with `make check`.
- Continuous integration and security tooling: CI, docs checks, secret scanning, CodeQL, dependency review, DCO check, automatic `security-sensitive` labeling of pull requests, `CODEOWNERS` and Dependabot.
- Community files: README (English and Spanish), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `GOVERNANCE.md`, issue forms and a pull request template.
- MIT license.

[Unreleased]: https://github.com/Turing0x/relevo/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Turing0x/relevo/releases/tag/v0.1.0
