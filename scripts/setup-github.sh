#!/usr/bin/env bash
# Configure the GitHub repository for relevo (ruleset, security, Actions, labels).
#
# !!! do NOT run this script without maintainer approval. !!!
# It belongs to Phase 5 (publication) of the open-source plan and changes the
# live repository settings. By default it is a DRY RUN: it only prints the
# commands it would run and never calls `gh` or the network. Pass --apply to
# execute them.
#
# Intended sequence (Phase 5): create the repo as private, push, run this
# script (dry-run, then --apply), check that CI is green, make the repo public,
# and run `--apply` again so the public-only steps (security features,
# CodeQL, dependency review) take effect. The script is idempotent.
#
# Usage:
#   scripts/setup-github.sh [--apply] [--help]
#   REPO=owner/name scripts/setup-github.sh        # default: Turing0x/relevo
#
# Requires: bash 3.2+, gh (authenticated with the `repo` and `workflow` scopes).
# NOT set on purpose: the repository homepage (the maintainer chose none).

set -euo pipefail

REPO="${REPO:-Turing0x/relevo}"

DESCRIPTION="Multi-model orchestrator for Claude Code: routes each task to haiku, sonnet or opus subagents, with hooks that enforce the safety-critical rules."
TOPICS="claude-code claude ai-agents multi-agent orchestration subagents llm developer-tools hooks"

# Required status checks of the "main protection" ruleset (job names).
REQUIRED_CHECKS="ci-ok docs-check gitleaks dco dependency-review"
# [PENDIENTE: verify on the first GET of the rulesets] GitHub Actions app id.
INTEGRATION_ID=15368
# Confirmed by the maintainer (bypass_mode: pull_request). RepositoryRole 5 = admin. With a single
# maintainer, without this bypass nobody can merge their own pull requests.
BYPASS_ACTOR_ID=5
RULESET_NAME="main protection"

# name|color|description
LABELS="bug|d73a4a|Something isn't working
enhancement|a2eeef|New feature or request
docs|0075ca|Documentation
good first issue|7057ff|Good for newcomers
help wanted|008672|Extra attention is needed
security-sensitive|b60205|Touches hooks, permissions, agent tools, prompts, installer or CI
new-agent|5319e7|Proposal for a new worker agent
question|d876e3|Further information is requested
dependencies|0366d6|Dependency updates (Dependabot)"

APPLY=0
VISIBILITY="unknown"
OK_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0
FAILED=""

usage() {
  cat <<'EOF'
Usage: scripts/setup-github.sh [--apply] [--help]

Configures the GitHub repository (default: Turing0x/relevo, override with REPO=owner/name):
  - repository settings (squash merge only, discussions, topics, description)
  - security features (public repositories only)
  - GitHub Actions permissions
  - the "main protection" ruleset
  - labels

Without --apply it is a dry run: it prints the commands and never calls gh.
Do NOT run with --apply without maintainer approval.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }

quote_arg() {
  case "$1" in
    ''|*[!A-Za-z0-9_./:=@%+,~-]*)
      printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
      ;;
    *) printf '%s' "$1" ;;
  esac
}

quote_cmd() {
  local out="" arg
  for arg in "$@"; do
    out="$out $(quote_arg "$arg")"
  done
  printf '%s' "${out# }"
}

record_ok() { OK_COUNT=$((OK_COUNT + 1)); say "OK    $1"; }
record_fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  FAILED="$FAILED
  - $1"
  say "FAIL  $1"
}
record_warn() { WARN_COUNT=$((WARN_COUNT + 1)); say "WARN  $1"; }
record_skip() { SKIP_COUNT=$((SKIP_COUNT + 1)); say "SKIP  $1"; }

# run_step LABEL CMD...   (set SOFT=1 to downgrade a failure to a warning)
run_step() {
  local label="$1" out
  shift
  if [ "$APPLY" -eq 0 ]; then
    say "DRY-RUN  $label"
    say "    \$ $(quote_cmd "$@")"
    return 0
  fi
  if out=$("$@" 2>&1 >/dev/null); then
    record_ok "$label"
  else
    if [ "${SOFT:-0}" = "1" ]; then
      record_warn "$label (not applied; see below)"
    else
      record_fail "$label"
    fi
    if [ -n "$out" ]; then
      printf '%s\n' "$out" | sed 's/^/        /'
    fi
  fi
  return 0
}

# run_json LABEL METHOD ENDPOINT JSON   (JSON goes to `gh api --input -`)
run_json() {
  local label="$1" method="$2" endpoint="$3" json="$4" out
  if [ "$APPLY" -eq 0 ]; then
    say "DRY-RUN  $label"
    say "    \$ gh api -X $method $endpoint --input - <<'JSON'"
    printf '%s\n' "$json"
    say "JSON"
    return 0
  fi
  if out=$(printf '%s\n' "$json" | gh api -X "$method" "$endpoint" --input - 2>&1 >/dev/null); then
    record_ok "$label"
  else
    if [ "${SOFT:-0}" = "1" ]; then
      record_warn "$label (not applied; see below)"
    else
      record_fail "$label"
    fi
    if [ -n "$out" ]; then
      printf '%s\n' "$out" | sed 's/^/        /'
    fi
  fi
  return 0
}

section() { say ""; say "== $1"; }

# ---------------------------------------------------------------- prerequisites
if [ "$APPLY" -eq 1 ]; then
  section "Prerequisites"
  if ! command -v gh >/dev/null 2>&1; then
    say "gh is not installed" >&2
    exit 1
  fi
  if ! status_out=$(gh auth status 2>&1); then
    say "gh is not authenticated: run 'gh auth login' (scopes: repo, workflow)" >&2
    exit 1
  fi
  if printf '%s\n' "$status_out" | grep -q "Token scopes"; then
    for scope in repo workflow; do
      if ! printf '%s\n' "$status_out" | grep "Token scopes" | grep -q "'$scope'"; then
        say "gh token lacks the '$scope' scope: run 'gh auth refresh -s $scope'" >&2
        exit 1
      fi
    done
  else
    say "note: cannot verify token scopes (fine-grained token?); continuing"
  fi
  VISIBILITY=$(gh repo view "$REPO" --json visibility --jq '.visibility' 2>/dev/null | tr '[:upper:]' '[:lower:]') || VISIBILITY=""
  if [ -z "$VISIBILITY" ]; then
    say "cannot read $REPO (does it exist and can this token see it?)" >&2
    exit 1
  fi
  say "Repository: $REPO ($VISIBILITY)"
else
  say "DRY RUN for $REPO (nothing is executed; pass --apply to run). Steps marked [public only] are skipped automatically while the repository is private."
fi

# ------------------------------------------------------------------- repository
section "Repository settings"
set -- repo edit "$REPO" \
  --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false \
  --delete-branch-on-merge --enable-discussions --enable-wiki=false --enable-projects=false \
  --description "$DESCRIPTION"
for topic in $TOPICS; do
  set -- "$@" --add-topic "$topic"
done
run_step "repo edit (merge methods, discussions, topics, description)" gh "$@"

run_step "squash commit format, sign-off required, update-branch button" \
  gh api -X PATCH "repos/$REPO" \
  -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=COMMIT_MESSAGES \
  -F web_commit_signoff_required=true \
  -F allow_update_branch=true

# --------------------------------------------------------------------- security
section "Security features [public only]"
if [ "$APPLY" -eq 1 ] && [ "$VISIBILITY" != "public" ]; then
  record_skip "secret scanning, push protection, Dependabot alerts/updates, private vulnerability reporting (repository is $VISIBILITY; re-run after making it public)"
else
  run_step "secret scanning + push protection" \
    gh repo edit "$REPO" --enable-secret-scanning --enable-secret-scanning-push-protection
  run_step "Dependabot alerts" gh api -X PUT "repos/$REPO/vulnerability-alerts"
  run_step "Dependabot security updates" gh api -X PUT "repos/$REPO/automated-security-fixes"
  run_step "private vulnerability reporting" gh api -X PUT "repos/$REPO/private-vulnerability-reporting"
fi

# ---------------------------------------------------------------------- actions
section "GitHub Actions permissions"
run_json "default workflow token is read-only; Actions cannot approve PRs" \
  PUT "repos/$REPO/actions/permissions/workflow" \
  '{"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}'
run_json "approval required for first-time contributors" \
  PUT "repos/$REPO/actions/permissions/fork-pr-contributor-approval" \
  '{"approval_policy":"first_time_contributors"}'
run_json "allow only selected actions; require SHA pinning" \
  PUT "repos/$REPO/actions/permissions" \
  '{"enabled":true,"allowed_actions":"selected","sha_pinning_required":true}'
run_json "selected actions: GitHub-owned plus lychee" \
  PUT "repos/$REPO/actions/permissions/selected-actions" \
  '{"github_owned_allowed":true,"verified_allowed":false,"patterns_allowed":["lycheeverse/lychee-action@*"]}'

# --------------------------------------------------------------------- ruleset
section "Ruleset: $RULESET_NAME"
checks_json=""
for check in $REQUIRED_CHECKS; do
  entry="{\"context\":\"$check\",\"integration_id\":$INTEGRATION_ID}"
  if [ -z "$checks_json" ]; then checks_json="$entry"; else checks_json="$checks_json,$entry"; fi
done
ruleset_json=$(cat <<EOF
{
  "name": "$RULESET_NAME",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [{"actor_id": $BYPASS_ACTOR_ID, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "required_linear_history"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": true,
      "require_last_push_approval": true,
      "required_review_thread_resolution": true,
      "allowed_merge_methods": ["squash"]
    }},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [$checks_json]
    }}
  ]
}
EOF
)
if [ "$APPLY" -eq 0 ]; then
  say "(would look up an existing ruleset named \"$RULESET_NAME\": PUT repos/$REPO/rulesets/{id} if it exists, POST repos/$REPO/rulesets otherwise)"
  run_json "create ruleset (POST shown; PUT when it already exists)" POST "repos/$REPO/rulesets" "$ruleset_json"
else
  ruleset_id=$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$RULESET_NAME\") | .id" 2>/dev/null | sed -n 1p) || ruleset_id=""
  # Rulesets on a private repository need a paid plan: warn instead of failing.
  if [ "$VISIBILITY" != "public" ]; then SOFT=1; else SOFT=0; fi
  if [ -n "$ruleset_id" ]; then
    run_json "update ruleset #$ruleset_id" PUT "repos/$REPO/rulesets/$ruleset_id" "$ruleset_json"
  else
    run_json "create ruleset" POST "repos/$REPO/rulesets" "$ruleset_json"
  fi
  SOFT=0
fi

# ---------------------------------------------------------------------- labels
section "Labels"
if [ "$APPLY" -eq 0 ]; then
  say "(if a label named \"documentation\" exists and \"docs\" does not, it is renamed first)"
  run_step "rename label documentation -> docs (only if present)" \
    gh label edit documentation --repo "$REPO" --name docs
else
  existing=$(gh label list --repo "$REPO" --limit 200 --json name --jq '.[].name' 2>/dev/null) || existing=""
  if printf '%s\n' "$existing" | grep -qx "documentation" && ! printf '%s\n' "$existing" | grep -qx "docs"; then
    run_step "rename label documentation -> docs" gh label edit documentation --repo "$REPO" --name docs
  fi
fi
while IFS='|' read -r label_name label_color label_desc; do
  [ -n "$label_name" ] || continue
  run_step "label: $label_name" \
    gh label create "$label_name" --repo "$REPO" --color "$label_color" --description "$label_desc" --force
done <<< "$LABELS"

# --------------------------------------------------------------------- summary
section "Manual steps (no API, or account level)"
cat <<'EOF'
  - Discussions: create the categories and forms in the web UI.
  - Upload the social preview image; pin the repository on the profile.
  - Security advisory notifications and 2FA (account settings).
  - Review the ruleset bypass and make sure code scanning is NOT on "default setup"
    (it conflicts with .github/workflows/codeql.yml).
  - Free plan: rulesets and GHAS do not apply to private repositories.
EOF

section "Summary"
if [ "$APPLY" -eq 0 ]; then
  say "Dry run finished. Nothing was changed."
  exit 0
fi
say "ok=$OK_COUNT warn=$WARN_COUNT skipped=$SKIP_COUNT failed=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  say "Failed steps:$FAILED"
  exit 1
fi
exit 0
