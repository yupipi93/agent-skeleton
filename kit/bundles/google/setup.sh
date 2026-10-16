#!/bin/bash
# setup.sh: connect the google bundle to your own OAuth client (bin/skeleton setup google).
#
#   1. Checks ~/.config/agent-skeleton/google/client.json (the Desktop client JSON you
#      downloaded from the Google Cloud console) and fixes its mode to 0600.
#   2. Offers to log in each tool (Chat, Docs, Gmail read-only) in the browser.
#
# Creating the client is a one-time console task: docs/bundles/google.md, "Setup".
# bash 3.2 compatible.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dir="${GOOGLE_OAUTH_DIR:-$HOME/.config/agent-skeleton/google}"
client="${GOOGLE_OAUTH_CLIENT:-$dir/client.json}"

yes_no() {
  local ans
  printf '%s (y/n) [%s]: ' "$1" "$2" >&2
  IFS= read -r ans || ans=""
  [ -n "$ans" ] || ans="$2"
  case "$ans" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac
}

mkdir -p "$dir" && chmod 700 "$dir"
if [ ! -f "$client" ]; then
  printf 'No OAuth client yet at %s\n\n' "$client"
  printf 'In the Google Cloud console of a project you own:\n'
  printf '  1. APIs & Services: enable the Google Chat, Google Docs, Google Drive and Gmail APIs\n'
  printf '     you want to use.\n'
  printf '  2. Google Auth Platform: configure the consent screen (Internal for a Workspace\n'
  printf '     organisation; External + Testing + yourself as a test user otherwise).\n'
  printf '  3. Clients > Create client > Desktop app > Download JSON.\n'
  printf '  4. Save it as %s and run this again.\n' "$client"
  printf '\nFull guide: docs/bundles/google.md\n'
  exit 1
fi
chmod 600 "$client"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); k=("installed" if "installed" in d else "web"); print("client ok: %s client %s..." % (k, d[k]["client_id"][:12]))' "$client" \
  || { printf 'error: %s is not a client JSON from the console\n' "$client" >&2; exit 1; }

if [ ! -t 0 ]; then
  printf 'Run the logins from a terminal:\n'
  for t in gchat gdocs gmail; do printf '  kit/bundles/google/scripts/%s.py login\n' "$t"; done
  exit 0
fi
for t in gchat gdocs gmail; do
  if [ -f "$dir/$t-token.json" ]; then
    printf '%s: already logged in (%s)\n' "$t" "$dir/$t-token.json"
    continue
  fi
  if yes_no "Log in $t now (opens the browser)?" n; then
    python3 "$here/scripts/$t.py" login || printf '%s: login failed, see above\n' "$t" >&2
  fi
done
printf '✅ google setup done\n'
