# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
