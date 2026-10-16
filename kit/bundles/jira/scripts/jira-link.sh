#!/usr/bin/env bash
#
# jira-link.sh: link two Jira issues (REST API v3).
#
# Usage:
#   kit/bundles/jira/scripts/jira-link.sh PROJ-1 PROJ-2                 # Relates
#   kit/bundles/jira/scripts/jira-link.sh PROJ-1 PROJ-2 --type Blocks   # PROJ-1 blocks PROJ-2
#   kit/bundles/jira/scripts/jira-link.sh PROJ-1 PROJ-2 --dry-run
#   kit/bundles/jira/scripts/jira-link.sh --list-types
#
# For directional types (Blocks, Cloners, Duplicate) the first key is the outward issue.
# Writes no text, so there is nothing to secret-scan.
# Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

TYPE="Relates" LIST=0 DRY_RUN=0 FROM="" TO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --type) atl_need_value "$1" $#; TYPE="$2"; shift 2 ;;
    --list-types) LIST=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *)
      if [ -z "$FROM" ]; then FROM="$1"
      elif [ -z "$TO" ]; then TO="$1"
      else echo "error: expected two issue keys" >&2; exit 2
      fi
      shift ;;
  esac
done

if [ "$LIST" -eq 0 ] && { [ -z "$FROM" ] || [ -z "$TO" ]; }; then
  usage >&2
  exit 2
fi

atl_load_site || exit 3
atl_tmp_init

if [ "$LIST" -eq 0 ]; then
  TYPE="$TYPE" FROM="$FROM" TO="$TO" python3 -c '
import json, os
print(json.dumps({"type": {"name": os.environ["TYPE"]},
                  "outwardIssue": {"key": os.environ["FROM"]},
                  "inwardIssue": {"key": os.environ["TO"]}}))' >"$ATL_TMPDIR/body.json"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry-run: POST https://${JIRA_SITE}/rest/api/3/issueLink"
    cat "$ATL_TMPDIR/body.json"
    exit 0
  fi
fi

atl_load_creds || exit 3

if [ "$LIST" -eq 1 ]; then
  atl_request GET /rest/api/3/issueLinkType || { atl_fail "listing link types"; exit 4; }
  python3 -c '
import json, sys
for t in json.load(open(sys.argv[1])).get("issueLinkTypes", []):
    print("%s\t(outward: %s / inward: %s)" % (t.get("name"), t.get("outward"), t.get("inward")))' "$ATL_RESPONSE"
  exit 0
fi

atl_request POST /rest/api/3/issueLink "$ATL_TMPDIR/body.json" || { atl_fail "link"; exit 4; }
echo "linked: ${FROM} --[${TYPE}]--> ${TO}"
