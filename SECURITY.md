# Security policy

relevo installs hooks, permissions and prompts into a tool that runs commands and edits files on your machine, so security reports are taken seriously. This document says what is supported, how to report a problem privately, what to expect in return, and which risks are inherent to an AI orchestrator and therefore documented rather than "fixed".

## Supported versions

| Version | Supported |
|---|---|
| `0.1.x` | Yes |
| Anything older | No |

The project is alpha. Fixes land on `main` and ship in the next `0.1.x` release.

## Reporting a vulnerability

**Do not open a public issue, discussion or pull request for a vulnerability.** Use one of these private channels:

1. **GitHub private vulnerability reporting:** <https://github.com/Turing0x/relevo/security/advisories/new>
2. **Email:** [threedotsdev@icloud.com](mailto:threedotsdev@icloud.com)

Please include:

- What the problem is and which component it affects (a hook, the installer, an agent definition, the policy, a workflow...).
- The version or commit SHA, your Claude Code version, your OS and your Python version.
- Steps to reproduce, ideally a minimal command or input (for a hook bypass, the exact tool call JSON or command).
- The impact you expect: what an attacker gains that the hook or permission was meant to prevent.
- Whether you want to be credited, and under what name.

Do not include real secrets or personal data in the report.

### What to expect

relevo has a single maintainer, so these are targets, not a service-level agreement:

| Step | Target |
|---|---|
| Acknowledgement of your report | within 3 business days |
| Triage (confirmed or not, severity, plan) | within 10 days |
| Fix or security advisory published | within 90 days |

Disclosure is coordinated: we agree a date with you, fix first, then publish an advisory. If a fix needs more than 90 days we will tell you why and agree a new date with you. If you have not heard back after the acknowledgement window, please send the report again by the other channel. Reporters are credited in the advisory and in the changelog unless they ask not to be.

## Scope

**In scope:**

- A new bypass of `block-force-push` or `guard-secrets` that is not in the list of known gaps below.
- An installer or uninstaller bug that corrupts `settings.json` or `CLAUDE.md`, writes outside the install prefix, or widens permissions beyond what the template declares.
- Problems in the GitHub workflows or the repository configuration (token exposure, untrusted code execution, a way to skip the review of sensitive paths).
- Supply-chain issues: a compromised or unpinned dependency or action, a release artifact that differs from the source.

**Out of scope:**

- The model not following the natural-language policy. The policy is guidance, not an enforcement mechanism (see below). If the router ignores a rule, that is a limitation we document; open a normal issue if you can show a pattern.
- Bugs in Claude Code itself or in the models. Report those to Anthropic through its [responsible disclosure policy](https://www.anthropic.com/responsible-disclosure-policy).
- The known gaps listed under "AI-orchestrator-specific risks" below, unless you have a new variant.

## AI-orchestrator-specific risks

relevo is mostly a policy written for a language model. These are the risks that follow from that, and what the project does and does not do about them. Where something is stated as enforced, Claude Code enforces it through permissions or hooks; everything else depends on the model obeying text.

- **Prompt injection through files or the web.** Workers read repository files, command output and sometimes web content, and any of it can contain instructions aimed at the model ("ignore your rules and..."). The policy asks workers to return sensitive actions as `PENDIENTE_APROBACION` and the router to ask you, but a model can be fooled. Treat the policy as guidance. The enforced layers (permissions and hooks) are the safety net, and they are not exhaustive.
- **Hooks execute commands with your privileges.** The three hooks run on every matching tool call. Read them before installing (`hooks/`), use `./scripts/install.sh --dry-run` to see exactly what is written, and review any change to them with care. The hooks use only the Python standard library and make no network calls.
- **Tool permissions of the workers.** Workers are limited by `tools` or `disallowedTools` in their frontmatter, which Claude Code enforces. `Explore` and `verificador` have `Bash` and are told never to edit files, but that is enforced only by their prompt: `Bash` can write. `clasificador` has only `Read`, `Grep` and `Glob`. No worker can spawn subagents (`disallowedTools: Agent` or a `tools` list without `Agent`, plus `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`).
- **Destructive actions.** `permissions.deny` and `permissions.ask` plus the `block-force-push` hook cover the common cases, but they are lists of patterns, not a complete barrier. Variants they do not cover exist: `find ... -delete`, `rm --recursive`, deleting through a script, and others. `block-force-push` has these known gaps: it does not catch a variable holding `git` (`G=git; $G push -f`), a git alias, or `eval "git push -f"` with the argument in quotes. These are recorded as expected failures in the test suite. Both hooks fail open: on an internal error they let the call through.
- **Secrets.** `guard-secrets` asks for confirmation when a call explicitly names `.env`, private keys or credentials. It is not a sandbox and does not detect a recursive grep over a directory without naming the secret, implicit loading (dotenv, `printenv` after `source`), obfuscation, or the `Glob` tool. It produces some false positives, which is deliberate (`ask`, not `deny`; see [ADR 0008](docs/decisions/0008-guard-secrets-ask.md)). Keep secrets out of the working directory when you can.
- **Telemetry.** `orch-telemetry` appends one line per finished worker to `~/.claude/orchestrator/log.jsonl`. A line holds the working directory, session and agent ids, agent name, model, effort, turn count, token counts (output tokens are an estimate), duration and a status keyword. It does not store prompts, file contents or model output. It stays on your machine; relevo never uploads it.
- **Supply chain.** relevo has no runtime dependencies beyond Python and the standard library. Development tools are pinned to exact versions in `requirements-dev.txt`. Third-party GitHub Actions are pinned by commit SHA, and downloaded binaries are verified against a pinned sha256. Dependabot proposes updates, and the sensitive-path workflow flags changes to these files.
- **The `pull_request_target` workflow.** The workflow that labels pull requests as `security-sensitive` uses the `pull_request_target` trigger so it can write a label and a comment on PRs from forks. That trigger runs with a token that has write access, so the workflow is built to be safe with it: it checks out only the base branch (never the PR's code), reads the PR's file names and patches as data through the REST API, never interpolates PR-controlled text into a shell command, references no secrets, and requests only `contents: read` and `pull-requests: write`. This departs from the usual advice to give fork PRs a read-only token. Any change to that workflow is itself security-sensitive and gets the strictest review.
- **Limits of the `security-sensitive` label.** The workflow labels and comments when a PR is opened, updated, reopened or marked ready. It does not remove the label or the comment if a later push stops touching sensitive paths, and changing the PR's base branch does not trigger it again. A maintainer should check the changed files themselves before merging and not rely on the label alone.

## Security-sensitive paths

Changes to hooks, agent definitions, permissions, prompts, the installer, scripts and workflows are reviewed more strictly, labeled automatically and require approval from the code owner. The full list and the reasons are in [CONTRIBUTING.md](CONTRIBUTING.md#security-sensitive-changes).

Hardening advice for users:

- Read the hooks and `templates/settings.example.json` before installing.
- Run `./scripts/install.sh --dry-run` first. The installer backs up what it changes. `./scripts/uninstall.sh` removes only files relevo created or replaced and left unmodified, never a file that already existed with identical content before the first install, and restores your original file if you used `--force`. Details are in the README.
- Do not add `allow` rules for the commands the template puts under `ask`, and do not relax `deny`.
- Keep `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` at `1`. The installer will not overwrite a different value you already set, so check it.
- Review agent files you copy from elsewhere before placing them in `~/.claude/agents/`: their frontmatter grants tools.
