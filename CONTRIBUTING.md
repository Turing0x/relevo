# Contributing to relevo

Thanks for your interest. relevo is a small, security-sensitive project: its hooks run commands on your machine and its prompts steer a model that can edit files. Please read [Security-sensitive changes](#security-sensitive-changes) before sending a PR that touches agents, hooks, permissions, prompts, the installer or CI.

By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). To report a vulnerability, do **not** open an issue; follow [SECURITY.md](SECURITY.md#reporting-a-vulnerability).

Questions and ideas are welcome in [GitHub Discussions](https://github.com/Turing0x/relevo/discussions). For larger changes, open an issue (or a discussion) first so we can agree on the approach before you write code.

## Development setup

You need `python3` 3.9 or newer and `git`. Hooks, `orchestrator/stats.py`, the installer, the `scripts/check_*.py` helpers and the tests use only the Python standard library and must stay compatible with Python 3.9.

```sh
git clone https://github.com/<your-user>/relevo.git
cd relevo
make test
```

`make install-dev` is optional. It creates `.venv` with a Python 3.11 or newer (the Makefile uses `DEV_PYTHON ?= python3.14`; override it if you have another version) and installs the pinned tools from `requirements-dev.txt` (ruff, mypy, jsonschema, zizmor, PyYAML). Only run it if you want the full lint and type checks locally.

**Never install into your real `~/.claude` to develop or test.** Point `HOME` at a throwaway directory instead:

```sh
HOME="$(mktemp -d)" ./scripts/install.sh --dry-run
HOME="$(mktemp -d)" ./scripts/install.sh
```

The test suite already does this: every subprocess it starts gets a temporary `HOME` and `ORCH_LOG`.

## Workflow

1. Fork the repository and create a branch from `main`.
2. Make your change, with tests and docs.
3. Run `make check` (see [Tests and lint](#tests-and-lint-locally)).
4. Commit with a sign-off and a Conventional Commits message.
5. Open a pull request against `main` and fill in the template.

PRs are merged by **squash**, so the PR title becomes the commit message on `main`: it must be a valid Conventional Commits title. Keep PRs small and focused; one concern per PR.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`.

- **Types:** `feat`, `fix`, `docs`, `test`, `ci`, `chore`, `refactor`, `perf`, `build`, `revert`.
- **Suggested scopes:** `agents`, `hooks`, `policy`, `install`, `stats`, `docs`, `ci`.

Examples: `fix(hooks): block git push with a leading -C option`, `docs(agents): clarify the arquitecto budget`.

## Code style

- **Python, new code:** `ruff` (lint and `ruff format`), line length 120, compatible with Python 3.9. Scripts under `scripts/` are checked with `mypy --strict`.
- **Existing hooks and `orchestrator/stats.py`** keep their current compact style. They are linted only for syntax errors and undefined names, and they are excluded from `ruff format`. Do not reformat them in unrelated changes.
- **Hooks use only the standard library**, run on Python 3.9, and read their input as JSON on stdin.
- **Hook output contracts** (documented in [`docs/decisions/`](docs/decisions/0008-guard-secrets-ask.md) and in the hooks' headers):
  - `block-force-push` blocks by exiting with code **2**.
  - `guard-secrets` prints a JSON `permissionDecision: "ask"` and exits **0**. It asks; it does not block.
  - `orch-telemetry` always exits **0** and never blocks.
- **Fail-open or fail-closed:** the hooks currently let the call through when they hit an internal error. Do not change that behavior without an ADR (see below).
- **Prose:** code, comments and community files are in English. The technical docs under `docs/` are currently in Spanish; match the language of the file you edit.
- Do not add runtime dependencies. If you think you need one, open an issue first.

## Tests and lint locally

| Command | What it does |
|---|---|
| `make check` | Everything below: `lint`, `lint-workflows`, `typecheck`, `test` and `docs-check` |
| `make test` | The `unittest` suite (standard library only) |
| `make lint` | Hidden-Unicode check, syntax compilation of every Python file and hook, `ruff check`, `ruff format --check` on new code, `shellcheck` |
| `make typecheck` | `mypy` on scripts (strict), tests, `stats.py` and each hook |
| `make docs-check` | Broken links and anchors, JSON Schema validity, and agent-to-doc consistency |
| `make lint-workflows` | `actionlint` and `zizmor` on `.github/workflows` |

If a tool is not installed, the local run prints `SKIP: <tool> not installed (run make install-dev)` and continues with exit code 0. That is expected on a bare machine: the tests and the docs checks still run. In CI (`CI` set) a missing tool is an error, so the full set of checks always runs there. Before opening a PR, make sure `make test` and `make docs-check` pass, and run the rest if you installed the dev tools.

Tests are black-box: they run the hooks and scripts through `subprocess` with `sys.executable`. Do not put real secrets in fixtures, not even fake-looking keys (secret scanning will flag them); use file names only.

## Proposing a new agent, or changing one

Open an issue with the **New agent** form first. A new agent changes cost, permissions and routing, so it needs agreement before code.

When the change is agreed, update all of these:

- `agents/<Name>.md`: the definition. The frontmatter `name` must equal the file name.
- `docs/agents/<Name>.md`: the agent's data sheet.
- `docs/contracts/<name>-output.schema.json`: the JSON Schema of its output (lowercase name).
- Routing table B in `orchestrator/policy.md` (section 2B) **and** its copy in `agents/clasificador.md`. The two must stay in sync.
- `docs/routing.md`, `docs/INDEX.md` and `docs/GLOSSARY.md`.
- A new ADR in `docs/decisions/` if the design changes.
- `CHANGELOG.md` (under `[Unreleased]`).

`make docs-check` verifies that every agent has its data sheet, its schema and an entry in `docs/INDEX.md` (and the reverse).

Changing an existing agent follows the same list, limited to the files that the change affects. Any change to `tools`, `disallowedTools`, `model`, `effort` or `maxTurns` is a change to permissions or cost and counts as [security-sensitive](#security-sensitive-changes).

## What we accept, and what we do not

**Welcome:**

- Bug fixes with a test that fails before the fix.
- New detection cases for `block-force-push` and `guard-secrets`, with tests (positive and negative).
- Documentation improvements and translations.
- More tests.
- New agents, after discussion in an issue.

**Not accepted:**

- Network calls or telemetry upload of any kind. Telemetry stays local.
- Runtime dependencies in the hooks.
- Relaxing a permission or a hook without an ADR that explains the trade-off.
- `allow` rules in the settings template.
- Hidden text in prompts (invisible or bidirectional Unicode, instructions in comments meant to be missed by a reviewer).
- CI that calls AI model APIs.
- Large rewrites of `docs/` without an issue first.

## Developer Certificate of Origin (DCO)

relevo uses the [Developer Certificate of Origin](https://developercertificate.org/) instead of a CLA. By signing off a commit you certify that you wrote the change or have the right to submit it under the project's MIT license.

Sign off every commit with `-s`:

```sh
git commit -s -m "fix(hooks): block git push with a leading -C option"
```

This appends a `Signed-off-by: Your Name <you@example.com>` line. The email must match the commit author's email. A CI check fails the PR if any non-merge commit lacks a matching sign-off (bot commits from Dependabot and GitHub Actions are exempt).

To fix it:

```sh
# last commit only
git commit --amend -s --no-edit

# every commit in your branch
git rebase --signoff origin/main
```

then `git push --force-with-lease` to **your own fork branch**. You can run the same check locally before pushing:

```sh
python3 scripts/check_dco.py origin/main HEAD
```

## Security-sensitive changes

Some paths define what runs on a user's machine and what the model is allowed to do. A pull request that touches them gets a stricter review. This is not distrust of contributors; it is that a small diff in these files can have a large effect:

- **Hooks run commands on the user's machine** on every tool call, with the user's privileges. A subtle change can open a hole or run something unexpected.
- **Agent frontmatter grants tools and models.** Adding `Bash` or `Edit`, or removing `disallowedTools: Agent`, changes what a worker can do and what it costs.
- **Prompts can hide instructions.** Invisible or bidirectional Unicode characters, or text buried in a long prompt, can steer the model in ways a reviewer does not see. CI scans for hidden characters, but a human still reads the diff.
- **The installer edits the user's `settings.json`** and `CLAUDE.md`, which control permissions for every project.
- **Workflows run with repository permissions.** A careless change can leak a token or run untrusted code.

The sensitive paths are:

```
.claude/**  **/CLAUDE.md  **/AGENTS.md  agents/**  hooks/**  commands/**  orchestrator/**  templates/**
scripts/**  .github/**  **/settings*.json  **/.mcp.json  **/*mcp*.json  Makefile  pyproject.toml
requirements*.txt  .gitattributes  **/.gitleaks.toml  **/.gitleaksignore
```

`docs/**`, `tests/**`, `README*`, `CHANGELOG.md` and the other community Markdown files are not on the list.

What happens when a PR touches one of them:

- A workflow adds the `security-sensitive` label and posts a comment summarizing the permission, tool and hook changes in the diff.
- The code owner, [@Turing0x](https://github.com/Turing0x), must review and approve (`.github/CODEOWNERS`).
- Please explain in the PR description what changes and why, and tick the matching box in the PR template. Changes that widen permissions, add tools or relax a hook are accepted only with a clear justification and, for design changes, an ADR.
