#!/usr/bin/env bash
#
# setup.sh: interactive configuration for the jira bundle (and the Bitbucket PR helper).
# Run it through the CLI:
#
#   bin/skeleton setup jira            # asks, then writes ~/.config/agent-skeleton/atlassian.env
#   bin/skeleton setup jira --dry-run  # asks, prints what would be written (no secrets), writes nothing
#
# Options:
#   --file PATH   write another file (default: $ATLASSIAN_ENV_FILE or ~/.config/agent-skeleton/atlassian.env)
#   --dry-run     write nothing
#
# Press Enter to keep the current value. Secrets are read without echo and stored through
# envfile.py on stdin, never on argv. The file is created with mode 0600 (directory 0700).
# Validation (GET /rest/api/3/myself) runs only if you say yes.

set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVFILE="$HERE/../core/scripts/lib/envfile.py"
FILE="${ATLASSIAN_ENV_FILE:-$HOME/.config/agent-skeleton/atlassian.env}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --file) [ $# -ge 2 ] || { echo "error: --file needs a path" >&2; exit 2; }; FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; exit 0 ;;
    *) echo "error: unknown argument $1" >&2; exit 2 ;;
  esac
done

if [ ! -t 0 ]; then
  echo "error: setup.sh is interactive; run it from a terminal (bin/skeleton setup jira)." >&2
  exit 2
fi

current() { python3 "$ENVFILE" get "$FILE" "$1" --no-env 2>/dev/null || true; }

PENDING=""   # newline-separated KEY names to write (values in VAL_<KEY>)

# ask KEY "Question" [default]: plain value.
ask() {
  local key="$1" question="$2" def cur ans
  cur="$(current "$key")"
  def="${cur:-${3-}}"
  if [ -n "$def" ]; then
    printf '%s [%s]: ' "$question" "$def"
  else
    printf '%s: ' "$question"
  fi
  IFS= read -r ans || ans=""
  [ -n "$ans" ] || ans="$def"
  if [ "$ans" = "-" ]; then ans=""; fi
  eval "VAL_$key=\$ans"
  PENDING="$PENDING $key"
}

# ask_secret KEY "Question": no echo; Enter keeps the current secret.
ask_secret() {
  local key="$1" question="$2" cur ans hint
  cur="$(current "$key")"
  hint=""
  [ -n "$cur" ] && hint=" [set, Enter keeps it]"
  printf '%s%s: ' "$question" "$hint"
  stty -echo 2>/dev/null || true
  IFS= read -r ans || ans=""
  stty echo 2>/dev/null || true
  printf '\n'
  [ -n "$ans" ] || ans="$cur"
  eval "VAL_$key=\$ans"
  PENDING="$PENDING $key"
}

yes_no() {
  local ans
  printf '%s [y/N]: ' "$1"
  IFS= read -r ans || ans=""
  case "$ans" in y|Y|yes|YES) return 0 ;; esac
  return 1
}

echo "Jira and Bitbucket settings for agent-skeleton -> $FILE"
echo "Enter keeps the value in brackets, '-' clears it."
echo

ask JIRA_SITE "Jira site (your-org.atlassian.net)"
ask JIRA_EMAIL "Atlassian account email (you@example.com)"
echo "API token: create one at https://id.atlassian.com/manage-profile/security/api-tokens"
ask_secret JIRA_API_TOKEN "Jira API token"
ask JIRA_DEFAULT_PROJECT "Default project key (PROJ, optional)"
ask JIRA_DEFAULT_ISSUETYPE "Default issue type" "Task"
ask JIRA_DEFAULT_ASSIGNEE "Default assignee: me, an accountId, or empty for Jira's default" "me"
ask JIRA_DEFAULT_REPORTER "Default reporter accountId (empty = the token owner)"
ask JIRA_LINK_STYLE "Ticket links: browse or portal (service desk customers)" "browse"
eval "style=\${VAL_JIRA_LINK_STYLE:-browse}"
if [ "$style" = "portal" ]; then
  ask JIRA_PORTAL_ID "Service desk portal id (the number in /servicedesk/customer/portal/<id>)"
fi

echo
if yes_no "Configure Bitbucket Cloud pull requests too?"; then
  ask BITBUCKET_WORKSPACE "Bitbucket workspace slug"
  ask BITBUCKET_EMAIL "Bitbucket Atlassian account email (empty = JIRA_EMAIL)"
  echo "Bitbucket token: an Atlassian API token with scopes read:repository:bitbucket and write:pullrequest:bitbucket"
  ask_secret BITBUCKET_API_TOKEN "Bitbucket API token"
fi
ask PR_DEFAULT_REVIEWERS "Default PR reviewers (comma-separated GitHub logins or Bitbucket account ids, optional)"

echo
if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: would write these keys to $FILE (values of secrets not shown):"
  for key in $PENDING; do
    eval "val=\${VAL_$key-}"
    case "$key" in
      *TOKEN*) [ -n "$val" ] && val="(secret)" ;;
    esac
    echo "  $key=$val"
  done
  exit 0
fi

for key in $PENDING; do
  eval "val=\${VAL_$key-}"
  if [ -n "$val" ]; then
    printf '%s' "$val" | python3 "$ENVFILE" set "$FILE" "$key"
  else
    python3 "$ENVFILE" unset "$FILE" "$key" >/dev/null 2>&1 || true
  fi
done
chmod 600 "$FILE"
chmod 700 "$(dirname "$FILE")" 2>/dev/null || true
echo "✅ wrote $FILE (mode 0600)"

if yes_no "Check the Jira credentials now (GET /rest/api/3/myself)?"; then
  # shellcheck source=scripts/lib/atlassian.sh
  ATLASSIAN_ENV_FILE="$FILE" . "$HERE/scripts/lib/atlassian.sh"
  ATL_CONFIG="$FILE"
  if atl_load_creds && atl_tmp_init && atl_request GET /rest/api/3/myself; then
    echo "✅ authenticated as $(atl_field "$ATL_RESPONSE" displayName)"
    cloud="$(atl_cloud_id)"
    if [ -n "$cloud" ] && [ -z "$(current JIRA_CLOUD_ID)" ]; then
      printf '%s' "$cloud" | python3 "$ENVFILE" set "$FILE" JIRA_CLOUD_ID
      echo "✅ stored JIRA_CLOUD_ID (used by the forms reader)"
    fi
  else
    atl_fail "credential check" || true
    echo "⚠️ check the site, the email and the token, then run: bin/skeleton setup jira"
    exit 1
  fi
fi
