#!/usr/bin/env bash
#
# pr-github.sh: open a GitHub pull request with a full, hand-written body (a thin
# wrapper around `gh pr create --body-file`).
#
# Usage:
#   kit/bundles/git/scripts/pr-github.sh --title "feat(api): add rate limits" --body-file pr.md \
#     [--ticket PROJ-123] [--reviewer alice] [--label infra] [--draft] [--dry-run]
#   kit/bundles/git/scripts/pr-github.sh --template > pr.md      # print the body scaffold
#
# Options:
#   --title TEXT        PR title (required; Conventional Commits style)
#   --body-file PATH    PR body in Markdown (required; '-' reads stdin)
#   --ticket KEY        append a ticket link (https://$JIRA_SITE/browse/KEY when JIRA_SITE
#                       is set in the environment or ~/.config/agent-skeleton/atlassian.env)
#   --reviewer LOGIN    repeatable; default PR_DEFAULT_REVIEWERS (comma-separated)
#   --no-default-reviewers   ignore PR_DEFAULT_REVIEWERS
#   --label NAME        repeatable
#   --base BRANCH       target branch (default: the repository default branch)
#   --head BRANCH       source branch (default: the current branch)
#   -C, --repo-dir DIR  run in DIR (default: current directory)
#   --draft             open as a draft
#   --no-section-check  allow a body without Summary, Changes, Validation and Rollback
#   --em-dash           also block U+2014 in title and body (house style)
#   --dry-run           print the gh command and the final body, change nothing
#   --template          print the body scaffold and exit
#
# The title and body go through kit/bundles/core/scripts/text-guard.sh first; a match
# blocks. Push the branch before running this (gh may otherwise offer to push).
# Exit codes: 0 ok, 2 usage, 3 gh missing or not authenticated, 4 gh failed, 5 blocked.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE="$HERE/../../core/scripts"
CFG="${ATLASSIAN_ENV_FILE:-$HOME/.config/agent-skeleton/atlassian.env}"
# shellcheck source=../../core/scripts/lib/secrets.sh
. "$CORE/lib/secrets.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

template() {
  cat <<'EOF'
## Summary
What changed and why, in two or three sentences.

## Changes
- Concrete list of edits

## Validation
- How it was verified (tests, plan output, manual checks)

## Rollback
- How to revert safely
EOF
}

need() { if [ "$2" -lt 2 ]; then echo "error: $1 needs a value" >&2; exit 2; fi; }

TITLE="" BODY_FILE="" TICKET="" BASE="" HEAD="" REPO_DIR="" DRAFT=0 DRY_RUN=0
SECTION_CHECK=1 USE_DEFAULTS=1 GUARD_ARGS="" REVIEWERS="" LABELS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --title) need "$1" $#; TITLE="$2"; shift 2 ;;
    --body-file) need "$1" $#; BODY_FILE="$2"; shift 2 ;;
    --ticket) need "$1" $#; TICKET="$2"; shift 2 ;;
    --reviewer) need "$1" $#; REVIEWERS="$REVIEWERS,$2"; shift 2 ;;
    --no-default-reviewers) USE_DEFAULTS=0; shift ;;
    --label) need "$1" $#; LABELS="$LABELS,$2"; shift 2 ;;
    --base) need "$1" $#; BASE="$2"; shift 2 ;;
    --head) need "$1" $#; HEAD="$2"; shift 2 ;;
    -C|--repo-dir) need "$1" $#; REPO_DIR="$2"; shift 2 ;;
    --draft) DRAFT=1; shift ;;
    --no-section-check) SECTION_CHECK=0; shift ;;
    --em-dash) GUARD_ARGS="--em-dash"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --template) template; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument $1" >&2; exit 2 ;;
  esac
done

[ -n "$TITLE" ] || { echo "error: --title is required" >&2; exit 2; }
[ -n "$BODY_FILE" ] || { echo "error: --body-file is required (never open a PR with an empty or generated body; --template prints a scaffold)" >&2; exit 2; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/pr-github.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
if [ "$BODY_FILE" = "-" ]; then
  cat >"$TMP/body.md"
else
  [ -r "$BODY_FILE" ] || { echo "error: cannot read --body-file $BODY_FILE" >&2; exit 2; }
  cat "$BODY_FILE" >"$TMP/body.md"
fi
[ -s "$TMP/body.md" ] || { echo "error: the PR body is empty" >&2; exit 2; }

if [ "$SECTION_CHECK" -eq 1 ]; then
  missing=""
  for s in Summary Changes Validation Rollback; do
    grep -Eq "^#{1,3}[[:space:]]+$s" "$TMP/body.md" || missing="$missing $s"
  done
  if [ -n "$missing" ]; then
    echo "error: the PR body lacks the section(s):$missing (see --template, or pass --no-section-check)" >&2
    exit 2
  fi
fi

if [ -n "$TICKET" ] && ! grep -q "$TICKET" "$TMP/body.md"; then
  site="$(secrets_get "$CFG" JIRA_SITE)"
  site="${site#https://}"
  site="${site%%/*}"
  if [ -n "$site" ]; then
    link="https://$site/browse/$TICKET"
  else
    link="$TICKET"
  fi
  printf '\n---\nTicket: %s\n' "$link" >>"$TMP/body.md"
fi

{ printf '%s\n\n' "$TITLE"; cat "$TMP/body.md"; } >"$TMP/outbound.md"
# shellcheck disable=SC2086
if ! /bin/bash "$CORE/text-guard.sh" --file "$TMP/outbound.md" $GUARD_ARGS; then
  echo "BLOCKED: the PR was not opened. Remove the secret-shaped text and retry." >&2
  exit 5
fi

if [ "$USE_DEFAULTS" -eq 1 ]; then
  REVIEWERS="$REVIEWERS,$(secrets_get "$CFG" PR_DEFAULT_REVIEWERS)"
fi

set -- gh pr create --title "$TITLE" --body-file "$TMP/body.md"
[ -n "$BASE" ] && set -- "$@" --base "$BASE"
[ -n "$HEAD" ] && set -- "$@" --head "$HEAD"
[ "$DRAFT" -eq 1 ] && set -- "$@" --draft
seen=","
old_ifs="$IFS"
IFS=','
set -f
for r in $REVIEWERS; do
  r="$(printf '%s' "$r" | tr -d '[:space:]')"
  [ -n "$r" ] || continue
  case "$seen" in *",$r,"*) continue ;; esac
  seen="$seen$r,"
  set -- "$@" --reviewer "$r"
done
for l in $LABELS; do
  [ -n "$l" ] && set -- "$@" --label "$l"
done
IFS="$old_ifs"
set +f

if [ "$DRY_RUN" -eq 1 ]; then
  [ -n "$REPO_DIR" ] && printf 'dry-run: in %s\n' "$REPO_DIR"
  printf 'dry-run:'
  printf ' %q' "$@"
  printf '\n--- body ---\n'
  cat "$TMP/body.md"
  exit 0
fi

if [ -n "$REPO_DIR" ]; then
  cd "$REPO_DIR" || { echo "error: cannot cd to $REPO_DIR" >&2; exit 2; }
fi
command -v gh >/dev/null 2>&1 || { echo "error: gh is not installed (brew install gh)" >&2; exit 3; }
gh auth status >/dev/null 2>&1 || { echo "error: gh is not authenticated; run: gh auth login" >&2; exit 3; }
"$@" || exit 4
