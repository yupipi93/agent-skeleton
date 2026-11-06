#!/usr/bin/env bash
#
# jira-share.sh: share a service desk request with people (request participants) and
# print the link they can open.
#
# Usage:
#   kit/bundles/jira/scripts/jira-share.sh PROJ-1 ada@example.com             # by email
#   kit/bundles/jira/scripts/jira-share.sh PROJ-1 712020:abc-123 bob@example.com
#   kit/bundles/jira/scripts/jira-share.sh PROJ-1 ada@example.com --dry-run
#   kit/bundles/jira/scripts/jira-share.sh PROJ-1 --list                      # who can see it
#
# An email is resolved to its account through the user search; anything else is taken
# as an accountId. People already sharing the request are skipped. The last line is the
# request's link: the customer portal when JIRA_PORTAL_ID is set (people without a Jira
# licence can only open that one), else the browse link.
# Writes no text, so there is nothing to secret-scan.
# Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error, 5 a person could not be resolved.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

KEY="" LIST=0 DRY_RUN=0
PEOPLE=()
while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *)
      if [ -z "$KEY" ]; then KEY="$1"; else PEOPLE+=("$1"); fi
      shift ;;
  esac
done

if [ -z "$KEY" ] || { [ "$LIST" -eq 0 ] && [ "${#PEOPLE[@]}" -eq 0 ]; }; then
  usage >&2
  exit 2
fi

atl_load_site || exit 3

# The portal link even when JIRA_LINK_STYLE is browse: participants are often customers.
share_url() {
  if [ -n "${JIRA_PORTAL_ID:-}" ]; then
    JIRA_LINK_STYLE=portal atl_issue_url "$1"
  else
    atl_issue_url "$1"
  fi
}

atl_load_creds || exit 3
atl_tmp_init

PARTICIPANTS_PATH="/rest/servicedeskapi/request/${KEY}/participant"

# Current participants as "accountId<TAB>displayName" lines, every page.
atl_request GET "${PARTICIPANTS_PATH}?limit=50" || { atl_fail "reading participants of $KEY"; exit 4; }
python3 -c '
import json, sys
for p in json.load(open(sys.argv[1])).get("values", []):
    print("%s\t%s" % (p.get("accountId", ""), p.get("displayName", "")))' "$ATL_RESPONSE" >"$ATL_TMPDIR/current.tsv"

if [ "$LIST" -eq 1 ]; then
  if [ -s "$ATL_TMPDIR/current.tsv" ]; then
    cat "$ATL_TMPDIR/current.tsv"
  else
    echo "(no participants)"
  fi
  share_url "$KEY"
  exit 0
fi

# Resolve each person to "accountId<TAB>displayName".
: >"$ATL_TMPDIR/wanted.tsv"
for who in "${PEOPLE[@]}"; do
  case "$who" in
    *@*)
      q="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$who")"
      atl_request GET "/rest/api/3/user/search?query=${q}" || { atl_fail "searching user $who"; exit 4; }
      line="$(WHO="$who" python3 -c '
import json, os, sys
who = os.environ["WHO"].lower()
users = [u for u in json.load(open(sys.argv[1]))
         if u.get("active", True) and u.get("accountType", "atlassian") != "app"]
exact = [u for u in users if (u.get("emailAddress") or "").lower() == who]
pick = exact or (users if len(users) == 1 else [])
if len(pick) == 1:
    print("%s\t%s" % (pick[0]["accountId"], pick[0].get("displayName", "")))' "$ATL_RESPONSE")"
      if [ -z "$line" ]; then
        echo "error: no single Jira account for $who; pass its accountId instead" >&2
        exit 5
      fi
      printf '%s\n' "$line" >>"$ATL_TMPDIR/wanted.tsv" ;;
    *) printf '%s\t%s\n' "$who" "$who" >>"$ATL_TMPDIR/wanted.tsv" ;;
  esac
done

# Drop the ones already sharing it; build the request body.
python3 -c '
import json, sys
current = {l.split("\t")[0] for l in open(sys.argv[1]) if l.strip()}
add, skip = [], []
for l in open(sys.argv[2]):
    acc, name = l.rstrip("\n").split("\t", 1)
    (skip if acc in current else add).append((acc, name))
json.dump({"accountIds": [a for a, _ in add]}, open(sys.argv[3], "w"))
open(sys.argv[4], "w").write(", ".join(n for _, n in add))
open(sys.argv[5], "w").write(", ".join(n for _, n in skip))' \
  "$ATL_TMPDIR/current.tsv" "$ATL_TMPDIR/wanted.tsv" "$ATL_TMPDIR/body.json" \
  "$ATL_TMPDIR/added.txt" "$ATL_TMPDIR/skipped.txt"

ADDED="$(cat "$ATL_TMPDIR/added.txt")"
SKIPPED="$(cat "$ATL_TMPDIR/skipped.txt")"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: POST https://${JIRA_SITE}${PARTICIPANTS_PATH}"
  cat "$ATL_TMPDIR/body.json"
  echo
elif [ -n "$ADDED" ]; then
  atl_request POST "$PARTICIPANTS_PATH" "$ATL_TMPDIR/body.json" || { atl_fail "sharing $KEY"; exit 4; }
fi

if [ -n "$ADDED" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then echo "would share: $KEY with $ADDED"; else echo "shared: $KEY with $ADDED"; fi
fi
[ -n "$SKIPPED" ] && echo "already shared with: $SKIPPED"
share_url "$KEY"
