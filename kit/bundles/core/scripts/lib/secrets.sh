# shellcheck shell=bash
# secrets.sh: helpers that keep secrets off the command line. Source it:
#
#   . "$(dirname "$0")/../../core/scripts/lib/secrets.sh"
#
# curl reads its credentials from a config passed on stdin (`curl -K -`), so tokens
# never show up in `ps` output or shell history. Because stdin carries the config,
# send request bodies with `--data-binary @file`, not `@-`.
#
# Values are read with envfile.py (no `source` of config files), and an environment
# variable with the same name always wins over the file.
#
# bash 3.2 compatible.

_secrets_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_CONFIG_DIR="${SECRETS_CONFIG_DIR:-$HOME/.config/agent-skeleton}"

# secrets_get FILE KEY [DEFAULT]: print the value (env var KEY overrides the file).
secrets_get() {
  local file="$1" key="$2" default="${3-}"
  local val
  if val="$(python3 "$_secrets_lib_dir/envfile.py" get "$file" "$key" 2>/dev/null)"; then
    printf '%s' "$val"
  else
    printf '%s' "$default"
  fi
}

# secrets_require FILE KEY...: fail (return 1) naming every missing key.
secrets_require() {
  local file="$1" key missing=""
  shift
  for key in "$@"; do
    if [ -z "$(secrets_get "$file" "$key")" ]; then
      missing="$missing $key"
    fi
  done
  if [ -n "$missing" ]; then
    printf 'missing config:%s (set them in %s or as environment variables)\n' "$missing" "$file" >&2
    return 1
  fi
}

# secrets_check_mode FILE: warn on stderr when the file is readable by group or others.
secrets_check_mode() {
  [ -e "$1" ] || return 0
  python3 "$_secrets_lib_dir/envfile.py" check-mode "$1" || true
}

# _secrets_curl_quote VALUE: escape for a double-quoted curl config value.
_secrets_curl_quote() {
  local v="$1"
  v="${v//\\/\\\\}"
  v="${v//\"/\\\"}"
  printf '%s' "$v"
}

# secrets_curl_basic USER SECRET [curl args...]: HTTP basic auth via stdin config.
secrets_curl_basic() {
  local user="$1" secret="$2"
  shift 2
  printf 'user = "%s:%s"\n' "$(_secrets_curl_quote "$user")" "$(_secrets_curl_quote "$secret")" \
    | curl -K - "$@"
}

# secrets_curl_bearer TOKEN [curl args...]: Authorization: Bearer via stdin config.
secrets_curl_bearer() {
  local token="$1"
  shift
  printf 'header = "Authorization: Bearer %s"\n' "$(_secrets_curl_quote "$token")" \
    | curl -K - "$@"
}

# secrets_curl_header "Name: value" [curl args...]: any secret header via stdin config.
secrets_curl_header() {
  local header="$1"
  shift
  printf 'header = "%s"\n' "$(_secrets_curl_quote "$header")" | curl -K - "$@"
}
