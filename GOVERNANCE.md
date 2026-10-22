# Governance

relevo is a small project with a single maintainer. This document says who decides what, how decisions are made, and how someone can become a maintainer. It is deliberately short and will grow if the project does.

## Maintainer

[@Turing0x](https://github.com/Turing0x) is the sole maintainer and has the final say on everything: the roadmap, what is merged, releases, and changes to this document.

## Decision making

- **Everyday changes** (bug fixes, docs, tests) are decided in the pull request. If the maintainer approves it and CI passes, it is merged.
- **Larger changes** (a new agent, a change of routing, budget or permissions, anything that touches a hook's behavior) are discussed first in an issue or in [GitHub Discussions](https://github.com/Turing0x/relevo/discussions). The goal is to agree on the approach before code is written.
- **Lazy consensus.** A proposal that has been open for a reasonable time (about a week for design changes) with no objection is considered accepted. Anyone can object; the maintainer weighs the objections and decides.
- **Design decisions are recorded as ADRs** in [`docs/decisions/`](docs/decisions/0001-politica-con-refuerzo-duro.md): context, decision, alternatives and consequences. A change that reverses or relaxes an earlier ADR needs a new ADR that says so. This is required, for example, to relax a permission or a hook, or to change a hook from fail-open to fail-closed.
- **Security reports** are handled privately, following [SECURITY.md](SECURITY.md#reporting-a-vulnerability), and are not discussed in public until a fix is ready.

## Sensitive paths

Paths that define permissions, tools, hooks, prompts, the installer or CI are listed in [CONTRIBUTING.md](CONTRIBUTING.md#security-sensitive-changes) and in `.github/CODEOWNERS`. Changes to them need the code owner's approval, whoever sends them. If there are more maintainers in the future, this rule stays: the code owners listed in `CODEOWNERS` must approve changes to these paths.

## Becoming a maintainer

There is no fixed checklist. Maintainers are invited by the current maintainer after sustained, good-quality contributions over time: code, reviews, triage, docs, or helping others in issues and discussions, together with a good understanding of the project's security model. If you are interested, say so in a discussion or by email; there is no need to wait for an invitation to start contributing.

A maintainer who is inactive for a long period, or who breaks the [Code of Conduct](CODE_OF_CONDUCT.md), may be asked to step down.

## Changing this document

Changes to the governance, the Code of Conduct or the security policy go through a pull request like any other change, and are decided by the maintainer after the discussion period above.
