#!/usr/bin/env bash
#
# jira-search.sh: run a JQL search (REST API v3, /search/jql) and print a Markdown table.
#
# Usage:
#   kit/bundles/jira/scripts/jira-search.sh 'project = PROJ AND status != Done ORDER BY updated DESC'
#   kit/bundles/jira/scripts/jira-search.sh 'project = PROJ AND summary ~ "login"' --max 10
#   kit/bundles/jira/scripts/jira-search.sh 'assignee = currentUser() AND statusCategory = "In Progress"'
#   kit/bundles/jira/scripts/jira-search.sh '<jql>' --json
#
# Options:
#   --max N    maximum results (default 20, capped at 100)
#   --json     raw JSON instead of the table
#
# Config: ~/.config/agent-skeleton/atlassian.env or environment variables.
# Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

JQL=""
MAX=20
AS_JSON=0
while [ $# -gt 0 ]; do
  case "$1" in
    --max) atl_need_value "$1" $#; MAX="$2"; shift 2 ;;
    --json) AS_JSON=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) JQL="$1"; shift ;;
  esac
done

[ -n "$JQL" ] || { usage >&2; exit 2; }
case "$MAX" in
  ''|*[!0-9]*|0) echo "error: --max needs a positive integer, got '$MAX'" >&2; exit 2 ;;
esac
[ "$MAX" -le 100 ] || MAX=100

atl_load_creds || exit 3
atl_tmp_init

JQL="$JQL" MAX="$MAX" python3 -c '
import json, os
print(json.dumps({"jql": os.environ["JQL"], "maxResults": int(os.environ["MAX"]),
                  "fields": ["summary", "status", "assignee", "reporter", "updated", "issuetype"]}))
' >"$ATL_TMPDIR/body.json"

atl_request POST /rest/api/3/search/jql "$ATL_TMPDIR/body.json" \
  || { atl_fail "search (check the JQL quoting)"; exit 4; }

if [ "$AS_JSON" -eq 1 ]; then
  cat "$ATL_RESPONSE"
  echo
else
  python3 "$ATL_JSON" search "$ATL_RESPONSE"
fi
