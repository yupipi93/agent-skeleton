#!/usr/bin/env bash
#
# jira-assign.sh: change the assignee of an existing Jira issue.
#
# Usage:
#   kit/bundles/jira/scripts/jira-assign.sh PROJ-1 ada@example.com     # by email
#   kit/bundles/jira/scripts/jira-assign.sh PROJ-1 712020:abc-123      # by accountId
#   kit/bundles/jira/scripts/jira-assign.sh PROJ-1 me                  # the token owner
#   kit/bundles/jira/scripts/jira-assign.sh PROJ-1 none                # unassign
#   kit/bundles/jira/scripts/jira-assign.sh PROJ-1 ada@example.com --dry-run
#
# An email is resolved to its account through the user search; anything else is taken
# as an accountId. Prints the new assignee and the issue link.
# Writes no text, so there is nothing to secret-scan.
# Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error, 5 the person could not be resolved.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

KEY="" WHO="" DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *)
      if [ -z "$KEY" ]; then KEY="$1"
      elif [ -z "$WHO" ]; then WHO="$1"
      else echo "error: one assignee only" >&2; exit 2
      fi
      shift ;;
  esac
done

if [ -z "$KEY" ] || [ -z "$WHO" ]; then
  usage >&2
  exit 2
fi

atl_load_site || exit 3
atl_load_creds || exit 3
atl_tmp_init

# Resolve to "accountId<TAB>displayName"; accountId "null" unassigns.
case "$WHO" in
  none) line="$(printf 'null\tnobody')" ;;
  me)
    atl_request GET "/rest/api/3/myself" || { atl_fail "reading the token owner"; exit 4; }
    line="$(python3 -c '
import json, sys
u = json.load(open(sys.argv[1]))
print("%s\t%s" % (u["accountId"], u.get("displayName", "")))' "$ATL_RESPONSE")" ;;
  *@*)
    q="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$WHO")"
    atl_request GET "/rest/api/3/user/search?query=${q}" || { atl_fail "searching user $WHO"; exit 4; }
    line="$(WHO="$WHO" python3 -c '
import json, os, sys
who = os.environ["WHO"].lower()
users = [u for u in json.load(open(sys.argv[1]))
         if u.get("active", True) and u.get("accountType", "atlassian") != "app"]
exact = [u for u in users if (u.get("emailAddress") or "").lower() == who]
pick = exact or (users if len(users) == 1 else [])
if len(pick) == 1:
    print("%s\t%s" % (pick[0]["accountId"], pick[0].get("displayName", "")))' "$ATL_RESPONSE")"
    if [ -z "$line" ]; then
      echo "error: no single Jira account for $WHO; pass its accountId instead" >&2
      exit 5
    fi ;;
  *) line="$(printf '%s\t%s' "$WHO" "$WHO")" ;;
esac

ACCOUNT="${line%%$'\t'*}"
NAME="${line#*$'\t'}"

python3 -c '
import json, sys
acc = sys.argv[1]
json.dump({"accountId": None if acc == "null" else acc}, open(sys.argv[2], "w"))' \
  "$ACCOUNT" "$ATL_TMPDIR/body.json"

ASSIGN_PATH="/rest/api/3/issue/${KEY}/assignee"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: PUT https://${JIRA_SITE}${ASSIGN_PATH}"
  cat "$ATL_TMPDIR/body.json"
  echo
  echo "would assign: $KEY to $NAME"
else
  atl_request PUT "$ASSIGN_PATH" "$ATL_TMPDIR/body.json" || { atl_fail "assigning $KEY"; exit 4; }
  echo "assigned: $KEY to $NAME"
fi
atl_issue_url "$KEY"
