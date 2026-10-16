#!/usr/bin/env bash
#
# jira-forms.sh: read the "Attached forms" (Jira Forms / ProForma) of an issue and print
# the answers as Markdown. Service desk requests often carry the real detail there, and
# Atlassian's MCP scopes cannot read forms; an API token can.
#
# Usage:
#   kit/bundles/jira/scripts/jira-forms.sh PROJ-123
#   kit/bundles/jira/scripts/jira-forms.sh PROJ-123 --json
#
# Options:
#   --json            raw form objects
#   --max-time SECS   per-request cap (default 10, so a hook can never hang)
#
# Uses https://api.atlassian.com/jira/forms/cloud/<cloud id>/... The cloud id comes from
# JIRA_CLOUD_ID, else the site's public tenant info.
# Config: ~/.config/agent-skeleton/atlassian.env or environment variables.
# Exit codes: 0 ok, 1 no forms attached, 2 usage, 3 missing config, 4 API error.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

KEY="" AS_JSON=0
JIRA_HTTP_TIMEOUT="${JIRA_FORMS_MAX_TIME:-10}"
while [ $# -gt 0 ]; do
  case "$1" in
    --json) AS_JSON=1; shift ;;
    --max-time) atl_need_value "$1" $#; JIRA_HTTP_TIMEOUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) KEY="$1"; shift ;;
  esac
done
[ -n "$KEY" ] || { usage >&2; exit 2; }
case "$JIRA_HTTP_TIMEOUT" in ''|*[!0-9]*) echo "error: --max-time needs seconds" >&2; exit 2 ;; esac
export JIRA_HTTP_TIMEOUT

atl_load_creds || exit 3
atl_tmp_init

CLOUD_ID="$(atl_cloud_id)"
if [ -z "$CLOUD_ID" ]; then
  echo "error: could not determine the cloud id of $JIRA_SITE; set JIRA_CLOUD_ID" >&2
  exit 3
fi
BASE="https://api.atlassian.com/jira/forms/cloud/${CLOUD_ID}/issue/${KEY}/form"
HDR="X-ExperimentalApi: opt-in"

atl_request GET "$BASE" "" "$HDR" || { atl_fail "listing the forms of ${KEY}"; exit 4; }
IDS="$(python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
for f in data if isinstance(data, list) else []:
    if f.get("id"):
        print(f["id"])' "$ATL_RESPONSE")"

if [ -z "$IDS" ]; then
  echo "no forms attached to ${KEY}" >&2
  exit 1
fi

n=0
FILES=""
for fid in $IDS; do
  case "$fid" in *[!A-Za-z0-9-]*) continue ;; esac
  if atl_request GET "$BASE/$fid" "" "$HDR"; then
    n=$((n + 1))
    cp "$ATL_RESPONSE" "$ATL_TMPDIR/form-$n.json"
    FILES="$FILES $ATL_TMPDIR/form-$n.json"
  fi
done

# shellcheck disable=SC2086
python3 - "$ATL_TMPDIR/forms.json" $FILES <<'PY'
import json, sys
forms = [json.load(open(p, encoding="utf-8")) for p in sys.argv[2:]]
json.dump(forms, open(sys.argv[1], "w", encoding="utf-8"))
PY

if [ "$AS_JSON" -eq 1 ]; then
  cat "$ATL_TMPDIR/forms.json"
  echo
else
  python3 "$ATL_JSON" forms "$ATL_TMPDIR/forms.json" "$KEY"
fi
