#!/usr/bin/env python3
"""Check that every commit in BASE..HEAD carries a matching DCO sign-off.

Usage: check_dco.py BASE HEAD

Each non-merge commit needs a ``Signed-off-by: Name <email>`` trailer whose email
matches the commit author's email (case-insensitive). Only the exact bot
addresses in EXEMPT_EMAILS are exempt. Exit status: 0 when all commits pass,
1 when one fails or the range cannot be read.

Standard library only; compatible with Python 3.9.
"""

from __future__ import annotations

import re
import subprocess
import sys

EXEMPT_EMAILS = frozenset(
    {
        "49699333+dependabot[bot]@users.noreply.github.com",
        "41898282+github-actions[bot]@users.noreply.github.com",
    }
)
SIGNOFF_RE = re.compile(r"^Signed-off-by:[ \t]*(\S.*?)[ \t]*<([^<>\s]+)>[ \t]*$", re.IGNORECASE | re.MULTILINE)
FIELD_SEP = "\x1f"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def signoff_emails(message: str) -> list[str]:
    """Return the lower-cased emails of all Signed-off-by trailers in ``message``."""
    return [m.group(2).lower() for m in SIGNOFF_RE.finditer(message)]


def check_commit(author_email: str, message: str) -> bool:
    if author_email in EXEMPT_EMAILS:
        return True
    return author_email.lower() in signoff_emails(message)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: check_dco.py BASE HEAD", file=sys.stderr)
        return 1
    base, head = argv[1], argv[2]
    try:
        shas = _git("rev-list", "--no-merges", f"{base}..{head}").split()
    except RuntimeError as exc:
        print(f"error: cannot list commits in {base}..{head}: {exc}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for sha in shas:
        try:
            raw = _git("show", "-s", f"--format=%ae{FIELD_SEP}%s{FIELD_SEP}%B", sha)
        except RuntimeError as exc:
            print(f"error: cannot read commit {sha}: {exc}", file=sys.stderr)
            return 1
        author_email, subject, message = raw.split(FIELD_SEP, 2)
        if not check_commit(author_email.strip(), message):
            failures.append(f"  {sha[:7]} {subject}")

    if not failures:
        print(f"DCO OK: {len(shas)} commit(s) checked.")
        return 0

    print("DCO check failed: these commits lack a Signed-off-by line matching their author email:")
    print("\n".join(failures))
    print()
    print("Fix the last commit:   git commit --amend -s --no-edit")
    print("Fix the whole branch:  git rebase --signoff origin/main")
    print("Then update the pull request:  git push --force-with-lease")
    print("See CONTRIBUTING.md#developer-certificate-of-origin-dco")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
