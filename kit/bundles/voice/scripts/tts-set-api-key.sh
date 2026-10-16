#!/bin/bash
# tts-set-api-key.sh [--unset] [--no-test]
#   Store a Google Cloud Text-to-Speech API key in ~/.config/agent-skeleton/notify.env.
#
#   kit/bundles/voice/scripts/tts-set-api-key.sh             # hidden prompt, validate, save
#   pbpaste | kit/bundles/voice/scripts/tts-set-api-key.sh   # or pipe it in
#   kit/bundles/voice/scripts/tts-set-api-key.sh --unset     # remove it
#
# Create the key in your Google Cloud project with the Text-to-Speech API enabled, and
# restrict it to texttospeech.googleapis.com:
#   gcloud services api-keys create --display-name=agent-tts \
#     --api-target=service=texttospeech.googleapis.com --project=my-project-id
#
# The key is never an argument (shell history, `ps`): it is read from a hidden prompt or
# stdin, validated against the voices endpoint (free, synthesises nothing) with the
# X-Goog-Api-Key header passed to curl on stdin, and only then written, at mode 0600.
# With the test enabled, a short phrase is synthesised (nothing is sent anywhere).
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../../.." && pwd)"
ENVFILE="$root/kit/bundles/core/scripts/lib/envfile.py"
CONF="${NOTIFY_CONFIG:-${AGENT_SKELETON_CONFIG_DIR:-$HOME/.config/agent-skeleton}/notify.env}"

unset_key=no
run_test=yes
while [ "$#" -gt 0 ]; do
  case "$1" in
    --unset)   unset_key=yes; shift ;;
    --no-test) run_test=no; shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'tts-set-api-key.sh: unexpected argument. The key is never passed as an\n' >&2
       printf 'argument: run the script and paste it at the prompt, or pipe it in.\n' >&2
       exit 2 ;;
  esac
done

mkdir -p "$(dirname "$CONF")" && chmod 700 "$(dirname "$CONF")" 2>/dev/null

if [ "$unset_key" = yes ]; then
  python3 "$ENVFILE" unset "$CONF" TTS_API_KEY >/dev/null 2>&1 || true
  printf 'TTS_API_KEY removed from %s\n' "$CONF"
  exit 0
fi

if [ -t 0 ]; then
  printf 'Paste the TTS API key (input hidden), then Enter: ' >&2
  IFS= read -rs key || key=""
  printf '\n' >&2
else
  IFS= read -r key || key=""
fi
# Trim whitespace and the quotes or comma a copy from JSON drags along.
key="$(printf '%s' "$key" | tr -d '[:space:]' | sed "s/^[\"',]*//; s/[\"',]*\$//")"
if [ -z "$key" ]; then
  printf 'tts-set-api-key.sh: nothing pasted, nothing changed.\n' >&2
  exit 2
fi
case "$key" in
  AIza*) : ;;
  *) printf 'tts-set-api-key.sh: Google API keys start with AIza; nothing was written.\n' >&2
     exit 2 ;;
esac
printf 'read a key of %d characters (...%s)\n' "${#key}" "${key: -4}"

resp="$(printf 'header = "X-Goog-Api-Key: %s"\n' "$key" \
  | curl -sS --max-time 20 -K - "https://texttospeech.googleapis.com/v1/voices?languageCode=en-US" 2>&1)"
verdict="$(printf '%s' "$resp" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("error unparseable response"); raise SystemExit
if isinstance(d, dict) and d.get("voices"):
    print("ok %d" % len(d["voices"])); raise SystemExit
err = (d.get("error") or {}) if isinstance(d, dict) else {}
print("error %s %s" % (err.get("status") or err.get("code") or "?", (err.get("message") or "")[:200]))
')"
case "$verdict" in
  ok\ *) printf 'key accepted (%s voices for en-US)\n' "${verdict#ok }" ;;
  *)
    printf 'tts-set-api-key.sh: the API rejected the key, nothing was written.\n  %s\n' "$verdict" >&2
    printf 'Common causes: a truncated paste (API_KEY_INVALID), the key restriction does not\n' >&2
    printf 'include texttospeech.googleapis.com, or the API is not enabled in the project.\n' >&2
    exit 1 ;;
esac

printf '%s' "$key" | python3 "$ENVFILE" set "$CONF" TTS_API_KEY
python3 "$ENVFILE" set "$CONF" TTS_ENGINE --value google
chmod 600 "$CONF"
printf 'wrote TTS_API_KEY and TTS_ENGINE=google to %s (0600)\n' "$CONF"

[ "$run_test" = no ] && exit 0
printf '\n--- synthesis check (nothing is sent) ---\n'
out_dir="$(mktemp -d "${TMPDIR:-/tmp}/tts-key-check.XXXXXX")"
trap 'rm -rf "$out_dir"' EXIT
if python3 "$here/voice-note.py" --engine google --no-send --no-hub --out "$out_dir/check.ogg" \
     --title "Key check" "The new key works."; then
  printf 'synthesised %s bytes of Ogg/Opus\n' "$(wc -c < "$out_dir/check.ogg" | tr -d ' ')"
  exit 0
fi
printf 'tts-set-api-key.sh: the key validated but synthesis failed, see above.\n' >&2
exit 1
