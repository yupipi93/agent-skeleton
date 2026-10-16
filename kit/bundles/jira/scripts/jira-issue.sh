#!/usr/bin/env bash
#
# jira-issue.sh: read a Jira issue (fields, description, attachments, every comment)
# through the REST API v3 and print it as Markdown.
#
# Usage:
#   kit/bundles/jira/scripts/jira-issue.sh PROJ-123             # header, description, comments
#   kit/bundles/jira/scripts/jira-issue.sh PROJ-123 --meta      # header only
#   kit/bundles/jira/scripts/jira-issue.sh PROJ-123 --comments  # comments only
#   kit/bundles/jira/scripts/jira-issue.sh PROJ-123 --json      # raw JSON (comments merged in)
#
# Comments are always worth reading: they carry the latest clarification or a changed
# ask. They are printed oldest first and paged until all of them are in.
#
# Config: ~/.config/agent-skeleton/atlassian.env (JIRA_SITE, JIRA_EMAIL, JIRA_API_TOKEN),
# each overridable by an environment variable. The token never appears on argv.
#
# Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

KEY=""
MODE="full"
while [ $# -gt 0 ]; do
  case "$1" in
    --meta) MODE="meta"; shift ;;
    --comments) MODE="comments"; shift ;;
    --json) MODE="json"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) KEY="$1"; shift ;;
  esac
done

if [ -z "$KEY" ]; then
  usage >&2
  exit 2
fi

atl_load_creds || exit 3
atl_tmp_init

FIELDS="summary,status,issuetype,priority,assignee,reporter,created,updated,labels,description,attachment,${JIRA_REQUEST_TYPE_FIELD}"
atl_request GET "/rest/api/3/issue/${KEY}?fields=${FIELDS}" || { atl_fail "reading ${KEY}"; exit 4; }
cp "$ATL_RESPONSE" "$ATL_TMPDIR/issue.json"

COMMENT_FILES=""
COMMENT_TOTAL=""
if [ "$MODE" = "meta" ]; then
  if atl_request GET "/rest/api/3/issue/${KEY}/comment?maxResults=0"; then
    COMMENT_TOTAL="$(atl_field "$ATL_RESPONSE" total)"
  fi
  [ -n "$COMMENT_TOTAL" ] || COMMENT_TOTAL="?"
else
  start=0
  page=0
  while :; do
    atl_request GET "/rest/api/3/issue/${KEY}/comment?maxResults=100&startAt=${start}&orderBy=created" \
      || { atl_fail "reading the comments of ${KEY}"; exit 4; }
    page=$((page + 1))
    cp "$ATL_RESPONSE" "$ATL_TMPDIR/comments-$page.json"
    COMMENT_FILES="$COMMENT_FILES $ATL_TMPDIR/comments-$page.json"
    total="$(atl_field "$ATL_RESPONSE" total)"
    start=$((start + 100))
    case "$total" in ''|*[!0-9]*) break ;; esac
    [ "$start" -lt "$total" ] || break
    [ "$page" -lt 50 ] || break
  done
fi

if [ "$MODE" = "json" ]; then
  # shellcheck disable=SC2086
  python3 "$ATL_JSON" merge-comments $COMMENT_FILES >"$ATL_TMPDIR/comments.json"
  python3 - "$ATL_TMPDIR/issue.json" "$ATL_TMPDIR/comments.json" <<'PY'
import json, sys
issue = json.load(open(sys.argv[1], encoding="utf-8"))
issue.setdefault("fields", {})["comment"] = json.load(open(sys.argv[2], encoding="utf-8"))
print(json.dumps(issue, indent=2, ensure_ascii=False))
PY
  exit 0
fi

# shellcheck disable=SC2086
COMMENT_TOTAL="$COMMENT_TOTAL" python3 "$ATL_JSON" issue "$ATL_TMPDIR/issue.json" $COMMENT_FILES --mode "$MODE"
