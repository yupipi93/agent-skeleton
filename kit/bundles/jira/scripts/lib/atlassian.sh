# shellcheck shell=bash
#
# atlassian.sh: shared Jira Cloud config and HTTP helpers for kit/bundles/jira/scripts.
# Source it, do not run it.
#
# Config: ~/.config/agent-skeleton/atlassian.env (KEY=VALUE, mode 0600), read with
# core's envfile.py and never `source`d. An environment variable with the same name
# always wins, and ATLASSIAN_ENV_FILE points at another file.
#
#   JIRA_SITE                 your-org.atlassian.net (required)
#   JIRA_EMAIL, JIRA_API_TOKEN  Basic auth for the REST API
#   JIRA_CLOUD_ID             forms API; fetched from the site when unset
#   JIRA_LINK_STYLE           browse (default) | portal, plus JIRA_PORTAL_ID
#   JIRA_REQUEST_TYPE_FIELD   service desk request type field (default customfield_10010)
#   JIRA_HTTP_TIMEOUT         seconds per request (default 30)
#
# Credentials reach curl through `curl -K -` (core secrets.sh), so stdin carries the
# curl config: request bodies always go in a file (--data-binary @file).
#
# bash 3.2 compatible.

ATL_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ATL_CORE_LIB="$(cd "$ATL_LIB_DIR/../../../core/scripts/lib" && pwd)"
# shellcheck source=../../../core/scripts/lib/secrets.sh
. "$ATL_CORE_LIB/secrets.sh"

ATL_CONFIG="${ATLASSIAN_ENV_FILE:-$SECRETS_CONFIG_DIR/atlassian.env}"
ATL_JSON="$ATL_LIB_DIR/jira_json.py"
ATL_TEXT_GUARD="$ATL_CORE_LIB/../text-guard.sh"
ATL_EMAIL=""
ATL_TOKEN=""
ATL_TMPDIR=""
ATL_STATUS=""
ATL_RESPONSE=""

# atl_get KEY [DEFAULT]: config value, env var first.
atl_get() { secrets_get "$ATL_CONFIG" "$1" "${2-}"; }

# atl_configured: true when the config file exists or JIRA_SITE is in the environment.
atl_configured() { [ -f "$ATL_CONFIG" ] || [ -n "${JIRA_SITE:-}" ]; }

# atl_load_site: set and export JIRA_SITE (host only), or explain how to set it.
atl_load_site() {
  local s
  s="$(atl_get JIRA_SITE)"
  s="${s#https://}"
  s="${s#http://}"
  s="${s%%/*}"
  if [ -z "$s" ]; then
    echo "error: JIRA_SITE is not set (for example your-org.atlassian.net)." >&2
    echo "Run 'bin/skeleton setup jira', or export JIRA_SITE=your-org.atlassian.net" >&2
    return 3
  fi
  JIRA_SITE="$s"
  JIRA_LINK_STYLE="$(atl_get JIRA_LINK_STYLE browse)"
  JIRA_PORTAL_ID="$(atl_get JIRA_PORTAL_ID)"
  JIRA_REQUEST_TYPE_FIELD="$(atl_get JIRA_REQUEST_TYPE_FIELD customfield_10010)"
  export JIRA_SITE JIRA_LINK_STYLE JIRA_PORTAL_ID JIRA_REQUEST_TYPE_FIELD
}

# atl_load_creds [--quiet]: site + email + token, or return 3 with a hint.
atl_load_creds() {
  atl_load_site || return 3
  ATL_EMAIL="$(atl_get JIRA_EMAIL)"
  ATL_TOKEN="$(atl_get JIRA_API_TOKEN)"
  if [ -z "$ATL_EMAIL" ] || [ -z "$ATL_TOKEN" ]; then
    if [ "${1-}" != "--quiet" ]; then
      echo "error: missing JIRA_EMAIL or JIRA_API_TOKEN in $ATL_CONFIG (or the environment)." >&2
      echo "Run 'bin/skeleton setup jira'. Create a token at https://id.atlassian.com/manage-profile/security/api-tokens" >&2
    fi
    return 3
  fi
  [ "${1-}" = "--quiet" ] || secrets_check_mode "$ATL_CONFIG"
  return 0
}

# atl_tmp_init: private temp dir removed on exit.
atl_tmp_init() {
  ATL_TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/agent-jira.XXXXXX")" || return 1
  chmod 700 "$ATL_TMPDIR"
  # shellcheck disable=SC2064
  trap "rm -rf '$ATL_TMPDIR'" EXIT
}

# atl_request METHOD PATH_OR_URL [BODY_FILE] [EXTRA_HEADER]
# Response body goes to $ATL_RESPONSE, status code to $ATL_STATUS (000 = transport
# failure). Returns 0 on 2xx, 4 otherwise.
atl_request() {
  local method="$1" target="$2" body="${3-}" extra="${4-}" url
  [ -n "$ATL_TMPDIR" ] || atl_tmp_init
  ATL_RESPONSE="$ATL_TMPDIR/response.$$.$RANDOM.json"
  case "$target" in
    http*) url="$target" ;;
    *) url="https://$JIRA_SITE$target" ;;
  esac
  set -- -sS --connect-timeout 10 --max-time "${JIRA_HTTP_TIMEOUT:-30}" -X "$method" \
    -H "Accept: application/json" -o "$ATL_RESPONSE" -w '%{http_code}'
  [ -n "$extra" ] && set -- "$@" -H "$extra"
  [ -n "$body" ] && set -- "$@" -H "Content-Type: application/json" --data-binary "@$body"
  ATL_STATUS="$(secrets_curl_basic "$ATL_EMAIL" "$ATL_TOKEN" "$@" "$url" 2>"$ATL_TMPDIR/curl.err")" \
    || ATL_STATUS="${ATL_STATUS:-000}"
  [ -n "$ATL_STATUS" ] || ATL_STATUS="000"
  [ -f "$ATL_RESPONSE" ] || : >"$ATL_RESPONSE"
  case "$ATL_STATUS" in
    2??) return 0 ;;
  esac
  return 4
}

# atl_fail WHAT: print a one-line error for the last request and return 4.
atl_fail() {
  if [ "$ATL_STATUS" = "000" ]; then
    echo "error: $1: could not reach https://$JIRA_SITE ($(head -c 200 "$ATL_TMPDIR/curl.err" 2>/dev/null))" >&2
  else
    echo "error: $1: HTTP $ATL_STATUS: $(python3 "$ATL_JSON" error "$ATL_RESPONSE")" >&2
  fi
  return 4
}

# atl_field FILE PATH: one value out of a JSON file (empty when absent).
atl_field() { python3 "$ATL_JSON" field "$1" "$2" 2>/dev/null || true; }

# atl_issue_url KEY: browse or portal link, per JIRA_LINK_STYLE.
atl_issue_url() {
  if [ "${JIRA_LINK_STYLE:-browse}" = "portal" ] && [ -n "${JIRA_PORTAL_ID:-}" ]; then
    printf 'https://%s/servicedesk/customer/portal/%s/%s\n' "$JIRA_SITE" "$JIRA_PORTAL_ID" "$1"
  else
    printf 'https://%s/browse/%s\n' "$JIRA_SITE" "$1"
  fi
}

# atl_cloud_id: JIRA_CLOUD_ID, else the site's public tenant info (no credentials).
atl_cloud_id() {
  local id
  id="$(atl_get JIRA_CLOUD_ID)"
  if [ -z "$id" ]; then
    id="$(curl -sS --connect-timeout 5 --max-time 10 "https://$JIRA_SITE/_edge/tenant_info" 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cloudId", ""))' 2>/dev/null || true)"
  fi
  printf '%s' "$id"
}

# atl_myself_id: accountId of the token owner.
atl_myself_id() {
  atl_request GET /rest/api/3/myself || { atl_fail "reading /myself"; return 4; }
  atl_field "$ATL_RESPONSE" accountId
}

# atl_guard FILE [--em-dash]: run the core text guard over FILE (exit 2 means blocked).
atl_guard() {
  local file="$1"
  shift
  /bin/bash "$ATL_TEXT_GUARD" --file "$file" "$@"
}

# atl_need_value FLAG NARGS: fail with a usage error when a flag has no value.
atl_need_value() {
  if [ "$2" -lt 2 ]; then
    echo "error: $1 needs a value" >&2
    exit 2
  fi
}
