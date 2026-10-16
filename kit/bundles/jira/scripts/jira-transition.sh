#!/usr/bin/env bash
#
# jira-transition.sh: move a Jira issue to another status (REST API v3).
#
# Usage:
#   kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --list
#   kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --to "In Progress"
#   kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --to Done
#   kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --to Done --dry-run
#   kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --id 31
#
# Options:
#   --list         transitions reachable from the current status
#   --to STATUS    target status name (case-insensitive), else a transition name
#   --id ID        a transition id you already know
#   --no-hops      fail instead of taking an intermediate step
#   --dry-run      resolve and print the plan, change nothing (still reads the issue)
#
# Resolution: exact status name, then exact transition name, then (for done, closed or
# resolved) the single non-cancelling transition into the done category, then a
# substring. When the target is not reachable, at most ONE hop through an in-progress
# status is taken, announced first. A cancellation (cancel, reject, decline, won't do,
# duplicate, abandon) is never used to reach Done; name it explicitly to cancel.
#
# Writes no text, so there is nothing to secret-scan.
# Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error or ambiguous target,
# 6 target not reachable.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

KEY="" TARGET="" TRANSITION_ID="" LIST_ONLY=0 ALLOW_HOPS=1 DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST_ONLY=1; shift ;;
    --to) atl_need_value "$1" $#; TARGET="$2"; shift 2 ;;
    --id) atl_need_value "$1" $#; TRANSITION_ID="$2"; shift 2 ;;
    --no-hops) ALLOW_HOPS=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *) KEY="$1"; shift ;;
  esac
done

[ -n "$KEY" ] || { usage >&2; exit 2; }
if [ "$LIST_ONLY" -eq 0 ] && [ -z "$TARGET" ] && [ -z "$TRANSITION_ID" ]; then
  echo "error: pass --list, --to STATUS or --id ID" >&2
  exit 2
fi
case "$TRANSITION_ID" in
  *[!0-9]*) echo "error: --id must be numeric, got '$TRANSITION_ID'" >&2; exit 2 ;;
esac

atl_load_creds || exit 3
atl_tmp_init
TJSON="$ATL_TMPDIR/transitions.json"

current_status() {
  atl_request GET "/rest/api/3/issue/${KEY}?fields=status" || { atl_fail "reading ${KEY}"; return 4; }
  atl_field "$ATL_RESPONSE" fields.status.name
}

fetch_transitions() {
  atl_request GET "/rest/api/3/issue/${KEY}/transitions" || { atl_fail "reading transitions"; return 4; }
  cp "$ATL_RESPONSE" "$TJSON"
}

apply_transition() {
  printf '{"transition":{"id":"%s"}}\n' "$1" >"$ATL_TMPDIR/body.json"
  atl_request POST "/rest/api/3/issue/${KEY}/transitions" "$ATL_TMPDIR/body.json" \
    || { atl_fail "applying transition $1"; return 4; }
}

STATUS="$(current_status)" || exit 4
fetch_transitions || exit 4

if [ "$LIST_ONLY" -eq 1 ]; then
  echo "${KEY} is in '${STATUS}'. Reachable from here:"
  python3 "$ATL_JSON" transitions "$TJSON"
  exit 0
fi

if [ -n "$TRANSITION_ID" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry-run: would apply transition ${TRANSITION_ID} to ${KEY} (now '${STATUS}')"
    exit 0
  fi
  apply_transition "$TRANSITION_ID" || exit 4
  echo "ok: ${KEY} '${STATUS}' -> '$(current_status)'"
  exit 0
fi

HOPS=0
while :; do
  rc=0
  MATCH="$(python3 "$ATL_JSON" resolve "$TARGET" "$TJSON")" || rc=$?
  [ "$rc" -eq 4 ] && exit 4
  if [ "$rc" -eq 0 ] && [ -n "$MATCH" ]; then
    ID="$(printf '%s' "$MATCH" | cut -f1)"
    NAME="$(printf '%s' "$MATCH" | cut -f2)"
    TO="$(printf '%s' "$MATCH" | cut -f3)"
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "dry-run: would apply '${NAME}' (${ID}) to ${KEY}: '${STATUS}' -> '${TO}'"
      exit 0
    fi
    apply_transition "$ID" || exit 4
    echo "ok: ${KEY} '${NAME}' applied, now in '$(current_status)'"
    exit 0
  fi

  if [ "$ALLOW_HOPS" -eq 0 ] || [ "$HOPS" -ge 1 ]; then
    echo "error: '${TARGET}' is not reachable from '${STATUS}'. Reachable now:" >&2
    python3 "$ATL_JSON" transitions "$TJSON" >&2
    exit 6
  fi
  HOP="$(python3 "$ATL_JSON" hop "$TJSON" || true)"
  if [ -z "$HOP" ]; then
    echo "error: '${TARGET}' is not reachable from '${STATUS}' and no in-progress step exists. Reachable now:" >&2
    python3 "$ATL_JSON" transitions "$TJSON" >&2
    exit 6
  fi
  HOP_ID="$(printf '%s' "$HOP" | cut -f1)"
  HOP_NAME="$(printf '%s' "$HOP" | cut -f2)"
  HOP_TO="$(printf '%s' "$HOP" | cut -f3)"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry-run: '${TARGET}' is not reachable from '${STATUS}'; would hop via '${HOP_NAME}' (${HOP_ID}) to '${HOP_TO}', then retry"
    exit 0
  fi
  echo "'${TARGET}' is not reachable from '${STATUS}'; hopping via '${HOP_NAME}' -> '${HOP_TO}'"
  apply_transition "$HOP_ID" || exit 4
  STATUS="$(current_status)" || exit 4
  fetch_transitions || exit 4
  HOPS=$((HOPS + 1))
done
