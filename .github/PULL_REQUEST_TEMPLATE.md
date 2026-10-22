## Summary

<!-- What does this PR change, and why? Keep it short. -->

## Linked issue

<!-- e.g. Closes #123. For larger changes, please open an issue or discussion first. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Tests
- [ ] CI / tooling
- [ ] Refactor
- [ ] Other:

## Checklist

- [ ] Tests added or updated and `make check` passes.
- [ ] Docs updated.
- [ ] Data sheets in `docs/agents/` and schemas in `docs/contracts/` updated if an agent or its output changes.
- [ ] `CHANGELOG.md` (Unreleased) updated.
- [ ] No secrets, personal data or absolute paths containing a username.
- [ ] Commits are signed off (DCO): `git commit -s`.
- [ ] PR title follows Conventional Commits.

## ⚠ Changes permissions, tools, hooks, prompts, installer or workflows?

These changes get extra review and the PR is labeled `security-sensitive` automatically (see [Security-sensitive changes](https://github.com/Turing0x/relevo/blob/main/CONTRIBUTING.md#security-sensitive-changes)). Tick everything that applies:

- [ ] Permissions (`permissions.allow` / `ask` / `deny`, or anything in a `settings*.json`)
- [ ] Agent tools, model or limits (`tools`, `disallowedTools`, `model`, `effort`, `maxTurns`)
- [ ] Hooks (`hooks/**`) or hook registration
- [ ] Prompts or policy (`orchestrator/**`, agent bodies, `CLAUDE.md`, `AGENTS.md`)
- [ ] Installer or scripts (`scripts/**`)
- [ ] GitHub workflows or other `.github/**` files
- [ ] None of the above

**If you ticked anything other than "None", explain what changes and why (required):**

<!-- What is different after this PR? Why is it needed? Does it widen what a worker or a hook can do? Is there an ADR in docs/decisions/? -->
