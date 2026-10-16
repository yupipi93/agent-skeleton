#!/usr/bin/env bash
#
# jira-create.sh: create a Jira issue (REST API v3) with a rich ADF description rendered
# from Markdown (headings, tables, lists, code, panels, emojis).
#
# Usage:
#   kit/bundles/jira/scripts/jira-create.sh --summary "Rotate the staging TLS cert" \
#     --description-file desc.md [--project PROJ] [--issuetype Task] [options]
#
# Options:
#   --project KEY          default JIRA_DEFAULT_PROJECT
#   --issuetype NAME       default JIRA_DEFAULT_ISSUETYPE, else "Task"
#   --summary TEXT         required
#   --description TEXT     or --description-file PATH (Markdown); one is required
#   --assignee ID          accountId, "me" (the token owner) or "none";
#                          default JIRA_DEFAULT_ASSIGNEE (empty = Jira decides)
#   --reporter ID          accountId; default JIRA_DEFAULT_REPORTER (empty = Jira decides)
#   --reporter-email EMAIL resolve a reporter by email (falls back to the default)
#   --request-type ID      service desk request type id, sent in JIRA_REQUEST_TYPE_FIELD
#   --priority NAME        e.g. Low, Medium, High
#   --parent KEY           parent issue (sub-tasks, or child issues of an epic)
#   --label NAME           repeatable
#   --em-dash              also block U+2014 (house style)
#   --dry-run              print the request and the payload, send nothing
#
# Safety: summary and description go through kit/bundles/core/scripts/text-guard.sh first,
# and the script refuses to send on a match. That backstop does not replace the review
# and approval the outbound-text-safety rule requires.
#
# Config: ~/.config/agent-skeleton/atlassian.env or environment variables.
# Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error, 5 blocked by the text guard.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/atlassian.sh
. "$HERE/lib/atlassian.sh"

usage() { awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; }

PROJECT="" ISSUETYPE="" SUMMARY="" DESCRIPTION="" DESC_FILE="" ASSIGNEE="" ASSIGNEE_SET=0
REPORTER="" REPORTER_EMAIL="" REQUEST_TYPE="" PRIORITY="" PARENT="" LABELS="" DRY_RUN=0
GUARD_ARGS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --project) atl_need_value "$1" $#; PROJECT="$2"; shift 2 ;;
    --issuetype) atl_need_value "$1" $#; ISSUETYPE="$2"; shift 2 ;;
    --summary) atl_need_value "$1" $#; SUMMARY="$2"; shift 2 ;;
    --description) atl_need_value "$1" $#; DESCRIPTION="$2"; shift 2 ;;
    --description-file) atl_need_value "$1" $#; DESC_FILE="$2"; shift 2 ;;
    --assignee) atl_need_value "$1" $#; ASSIGNEE="$2"; ASSIGNEE_SET=1; shift 2 ;;
    --reporter) atl_need_value "$1" $#; REPORTER="$2"; shift 2 ;;
    --reporter-email) atl_need_value "$1" $#; REPORTER_EMAIL="$2"; shift 2 ;;
    --request-type) atl_need_value "$1" $#; REQUEST_TYPE="$2"; shift 2 ;;
    --priority) atl_need_value "$1" $#; PRIORITY="$2"; shift 2 ;;
    --parent) atl_need_value "$1" $#; PARENT="$2"; shift 2 ;;
    --label) atl_need_value "$1" $#; LABELS="${LABELS}${2}
"; shift 2 ;;
    --em-dash) GUARD_ARGS="--em-dash"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument $1" >&2; exit 2 ;;
  esac
done

if [ -n "$DESC_FILE" ]; then
  [ -r "$DESC_FILE" ] || { echo "error: cannot read --description-file $DESC_FILE" >&2; exit 2; }
fi

atl_load_site || exit 3
atl_tmp_init

[ -n "$PROJECT" ] || PROJECT="$(atl_get JIRA_DEFAULT_PROJECT)"
[ -n "$ISSUETYPE" ] || ISSUETYPE="$(atl_get JIRA_DEFAULT_ISSUETYPE Task)"
[ "$ASSIGNEE_SET" -eq 1 ] || ASSIGNEE="$(atl_get JIRA_DEFAULT_ASSIGNEE)"
[ "$ASSIGNEE" = "none" ] && ASSIGNEE=""
[ -n "$REPORTER" ] || [ -n "$REPORTER_EMAIL" ] || REPORTER="$(atl_get JIRA_DEFAULT_REPORTER)"

if [ -z "$PROJECT" ] || [ -z "$SUMMARY" ] || { [ -z "$DESCRIPTION" ] && [ -z "$DESC_FILE" ]; }; then
  echo "error: --summary, --description(-file) and a project (--project or JIRA_DEFAULT_PROJECT) are required" >&2
  exit 2
fi

# Text guard over everything that leaves the machine.
{
  printf '%s\n\n' "$SUMMARY"
  if [ -n "$DESC_FILE" ]; then cat "$DESC_FILE"; else printf '%s\n' "$DESCRIPTION"; fi
} >"$ATL_TMPDIR/outbound.md"
# shellcheck disable=SC2086
if ! atl_guard "$ATL_TMPDIR/outbound.md" $GUARD_ARGS; then
  echo "BLOCKED: nothing was sent. Reword the text (reference secrets by name, never by value)." >&2
  exit 5
fi

if [ "$DRY_RUN" -eq 0 ]; then
  atl_load_creds || exit 3
  if [ "$ASSIGNEE" = "me" ]; then
    ASSIGNEE="$(atl_myself_id)" || exit 4
  fi
  if [ -z "$REPORTER" ] && [ -n "$REPORTER_EMAIL" ]; then
    q="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$REPORTER_EMAIL")"
    if atl_request GET "/rest/api/3/user/search?query=${q}"; then
      REPORTER="$(python3 -c '
import json, sys
users = [u for u in json.load(open(sys.argv[1])) if u.get("active", True)]
humans = [u for u in users if u.get("accountType") == "atlassian"] or users
print(humans[0]["accountId"] if humans else "")' "$ATL_RESPONSE" 2>/dev/null || true)"
    fi
    if [ -n "$REPORTER" ]; then
      echo "reporter: resolved $REPORTER_EMAIL" >&2
    else
      REPORTER="$(atl_get JIRA_DEFAULT_REPORTER)"
      echo "warning: no Jira account found for $REPORTER_EMAIL; using the default reporter" >&2
    fi
  fi
fi

PROJECT="$PROJECT" ISSUETYPE="$ISSUETYPE" SUMMARY="$SUMMARY" DESCRIPTION="$DESCRIPTION" \
DESCRIPTION_FILE="$DESC_FILE" ASSIGNEE="$ASSIGNEE" REPORTER="$REPORTER" \
REQUEST_TYPE="$REQUEST_TYPE" PRIORITY="$PRIORITY" PARENT="$PARENT" LABELS="$LABELS" \
  python3 "$ATL_JSON" create-payload >"$ATL_TMPDIR/payload.json"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: POST https://${JIRA_SITE}/rest/api/3/issue"
  [ "$ASSIGNEE" = "me" ] && echo "dry-run: assignee 'me' is resolved through /myself when sending"
  [ -n "$REPORTER_EMAIL" ] && echo "dry-run: reporter $REPORTER_EMAIL is resolved through /user/search when sending"
  cat "$ATL_TMPDIR/payload.json"
  exit 0
fi

atl_request POST /rest/api/3/issue "$ATL_TMPDIR/payload.json" || { atl_fail "create"; exit 4; }
NEW_KEY="$(atl_field "$ATL_RESPONSE" key)"
echo "created: $NEW_KEY"
echo "url: $(atl_issue_url "$NEW_KEY")"
