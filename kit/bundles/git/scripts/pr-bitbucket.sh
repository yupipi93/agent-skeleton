#!/usr/bin/env bash
#
# pr-bitbucket.sh: open a Bitbucket Cloud pull request with a full, hand-written body
# through the REST API (never Bitbucket's auto-generated description).
#
# Usage:
#   kit/bundles/git/scripts/pr-bitbucket.sh --title "fix(dns): correct TTL" --body-file pr.md \
#     [--ticket PROJ-123] [--reviewer '{uuid}' | --reviewer 557058:abcd...] [--dry-run]
#   kit/bundles/git/scripts/pr-bitbucket.sh --template > pr.md
#
# Options:
#   --title TEXT         PR title (required)
#   --body-file PATH     PR body in Markdown (required; '-' reads stdin)
#   --repo SLUG          repository slug (default: from the origin remote)
#   --workspace WS       workspace (default: BITBUCKET_WORKSPACE, else the origin remote)
#   --source BRANCH      source branch (default: the current branch)
#   --dest BRANCH        destination (default: origin's HEAD branch, else main)
#   --ticket KEY         append a ticket link (uses JIRA_SITE when set)
#   --reviewer ID        Bitbucket account_id or {uuid}; repeatable;
#                        default PR_DEFAULT_REVIEWERS (comma-separated)
#   --no-default-reviewers   ignore PR_DEFAULT_REVIEWERS
#   --no-close-source    keep the source branch after merge (default: close it)
#   -C, --repo-dir DIR   repository to read branch and remote from (default: .)
#   --no-section-check   allow a body without Summary, Changes, Validation and Rollback
#   --em-dash            also block U+2014 (house style)
#   --dry-run            print the request and payload, send nothing
#   --template           print the body scaffold and exit
#
# Credentials: ~/.config/agent-skeleton/atlassian.env (or environment variables):
#   BITBUCKET_EMAIL (falls back to JIRA_EMAIL) and BITBUCKET_API_TOKEN, an Atlassian API
#   token with scopes read:repository:bitbucket and write:pullrequest:bitbucket.
#   They reach curl through `curl -K -` on stdin, never argv.
# Exit codes: 0 ok, 2 usage, 3 missing credentials, 4 API error, 5 blocked by the text guard.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE="$HERE/../../core/scripts"
CFG="${ATLASSIAN_ENV_FILE:-$HOME/.config/agent-skeleton/atlassian.env}"
API="${BITBUCKET_API:-https://api.bitbucket.org/2.0}"
# shellcheck source=../../core/scripts/lib/secrets.sh
. "$CORE/lib/secrets.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }
need() { if [ "$2" -lt 2 ]; then echo "error: $1 needs a value" >&2; exit 2; fi; }

TITLE="" BODY_FILE="" REPO="" WORKSPACE="" SOURCE="" DEST="" TICKET="" REPO_DIR="."
REVIEWERS="" USE_DEFAULTS=1 CLOSE_SOURCE=true SECTION_CHECK=1 GUARD_ARGS="" DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --title) need "$1" $#; TITLE="$2"; shift 2 ;;
    --body-file) need "$1" $#; BODY_FILE="$2"; shift 2 ;;
    --repo) need "$1" $#; REPO="$2"; shift 2 ;;
    --workspace) need "$1" $#; WORKSPACE="$2"; shift 2 ;;
    --source) need "$1" $#; SOURCE="$2"; shift 2 ;;
    --dest) need "$1" $#; DEST="$2"; shift 2 ;;
    --ticket) need "$1" $#; TICKET="$2"; shift 2 ;;
    --reviewer) need "$1" $#; REVIEWERS="$REVIEWERS,$2"; shift 2 ;;
    --no-default-reviewers) USE_DEFAULTS=0; shift ;;
    --no-close-source) CLOSE_SOURCE=false; shift ;;
    -C|--repo-dir) need "$1" $#; REPO_DIR="$2"; shift 2 ;;
    --no-section-check) SECTION_CHECK=0; shift ;;
    --em-dash) GUARD_ARGS="--em-dash"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --template) /bin/bash "$HERE/pr-github.sh" --template; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument $1" >&2; exit 2 ;;
  esac
done

[ -n "$TITLE" ] || { echo "error: --title is required" >&2; exit 2; }
[ -n "$BODY_FILE" ] || { echo "error: --body-file is required (--template prints a scaffold)" >&2; exit 2; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/pr-bitbucket.XXXXXX")"
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

# Repository coordinates from the origin remote when not given. SSH remotes may use
# either bitbucket.org or ssh.bitbucket.org (Bitbucket's dedicated SSH host).
remote="$(git -C "$REPO_DIR" remote get-url origin 2>/dev/null || true)"
path="$(printf '%s' "$remote" | sed -E 's#^(https?://([^@/]+@)?bitbucket\.org/|git@(ssh\.)?bitbucket\.org:|ssh://git@(ssh\.)?bitbucket\.org/)##; s#\.git$##')"
if [ "$path" != "$remote" ] && [ -n "$path" ]; then
  [ -n "$WORKSPACE" ] || WORKSPACE="${path%%/*}"
  [ -n "$REPO" ] || REPO="${path#*/}"
fi
[ -n "$WORKSPACE" ] || WORKSPACE="$(secrets_get "$CFG" BITBUCKET_WORKSPACE)"
[ -n "$WORKSPACE" ] || { echo "error: no workspace (--workspace, BITBUCKET_WORKSPACE or a bitbucket.org origin)" >&2; exit 2; }
[ -n "$REPO" ] || { echo "error: no repository (--repo, or run inside a clone with a bitbucket.org origin)" >&2; exit 2; }
[ -n "$SOURCE" ] || SOURCE="$(git -C "$REPO_DIR" symbolic-ref --short HEAD 2>/dev/null || true)"
[ -n "$SOURCE" ] || { echo "error: no source branch (--source, or run on a branch)" >&2; exit 2; }
if [ -z "$DEST" ]; then
  DEST="$(git -C "$REPO_DIR" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  DEST="${DEST#origin/}"
  [ -n "$DEST" ] || DEST="main"
fi

if [ -n "$TICKET" ] && ! grep -q "$TICKET" "$TMP/body.md"; then
  site="$(secrets_get "$CFG" JIRA_SITE)"
  site="${site#https://}"
  site="${site%%/*}"
  if [ -n "$site" ]; then link="https://$site/browse/$TICKET"; else link="$TICKET"; fi
  printf '\n---\nTicket: %s\n' "$link" >>"$TMP/body.md"
fi

{ printf '%s\n\n' "$TITLE"; cat "$TMP/body.md"; } >"$TMP/outbound.md"
# shellcheck disable=SC2086
if ! /bin/bash "$CORE/text-guard.sh" --file "$TMP/outbound.md" $GUARD_ARGS; then
  echo "BLOCKED: the PR was not opened. Remove the secret-shaped text and retry." >&2
  exit 5
fi

[ "$USE_DEFAULTS" -eq 1 ] && REVIEWERS="$REVIEWERS,$(secrets_get "$CFG" PR_DEFAULT_REVIEWERS)"

TITLE="$TITLE" SOURCE="$SOURCE" DEST="$DEST" CLOSE="$CLOSE_SOURCE" REVIEWERS="$REVIEWERS" \
  python3 - "$TMP/body.md" >"$TMP/payload.json" <<'PY'
import json, os, sys
ids = []
for r in os.environ.get("REVIEWERS", "").split(","):
    r = r.strip()
    if r and r not in ids:
        ids.append(r)
payload = {
    "title": os.environ["TITLE"],
    "source": {"branch": {"name": os.environ["SOURCE"]}},
    "destination": {"branch": {"name": os.environ["DEST"]}},
    "description": open(sys.argv[1], encoding="utf-8").read(),
    "close_source_branch": os.environ["CLOSE"] == "true",
}
if ids:
    payload["reviewers"] = [{"uuid": r} if r.startswith("{") else {"account_id": r} for r in ids]
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY

URL="$API/repositories/$WORKSPACE/$REPO/pullrequests"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: POST $URL"
  cat "$TMP/payload.json"
  exit 0
fi

EMAIL="$(secrets_get "$CFG" BITBUCKET_EMAIL)"
[ -n "$EMAIL" ] || EMAIL="$(secrets_get "$CFG" JIRA_EMAIL)"
TOKEN="$(secrets_get "$CFG" BITBUCKET_API_TOKEN)"
if [ -z "$EMAIL" ] || [ -z "$TOKEN" ]; then
  echo "error: missing BITBUCKET_EMAIL (or JIRA_EMAIL) and BITBUCKET_API_TOKEN in $CFG or the environment." >&2
  echo "Run 'bin/skeleton setup jira' and answer yes to the Bitbucket question." >&2
  exit 3
fi
secrets_check_mode "$CFG"

code="$(secrets_curl_basic "$EMAIL" "$TOKEN" -sS --connect-timeout 10 --max-time 60 \
  -X POST -H "Content-Type: application/json" -H "Accept: application/json" \
  --data-binary "@$TMP/payload.json" -o "$TMP/response.json" -w '%{http_code}' \
  "$URL" 2>"$TMP/curl.err")" || true
case "$code" in
  200|201)
    python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print("ok: PR #%s %s" % (d.get("id", "?"), ((d.get("links") or {}).get("html") or {}).get("href", "")))' "$TMP/response.json"
    ;;
  ''|000)
    echo "error: could not reach the Bitbucket API: $(head -c 300 "$TMP/curl.err")" >&2
    exit 4 ;;
  *)
    echo "error: Bitbucket API returned HTTP $code" >&2
    python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print((d.get("error") or {}).get("message") or json.dumps(d)[:500])
except Exception:
    print(open(sys.argv[1], errors="replace").read()[:500])' "$TMP/response.json" >&2 || true
    exit 4 ;;
esac
