#!/bin/bash
# notify-setup.sh: interactive setup of the voice bundle (bin/skeleton setup voice).
#
#   kit/bundles/voice/scripts/notify-setup.sh          # the wizard
#   kit/bundles/voice/scripts/notify-setup.sh --show   # which keys are set (never values)
#
# Writes ~/.config/agent-skeleton/notify.env (mode 0600, directory 0700):
#   1. Telegram: validates the bot token, discovers your chat id from getUpdates.
#   2. Google Chat: an incoming webhook URL (text and cards), optionally a space for audio.
#   3. Text to speech: Google Cloud TTS with an API key, else the macOS `say` voice,
#      else none (summaries go out as text).
#   4. Language, your name for the greeting, the optional local voice hub.
#   5. A test message and a test voice note, only if you say yes.
#
# Secrets are read with a hidden prompt, reach curl through a config on stdin (`curl -K -`)
# and are stored with envfile.py on stdin: never on a command line, never echoed back.
# bash 3.2 compatible.
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../../.." && pwd)"
ENVFILE="$root/kit/bundles/core/scripts/lib/envfile.py"
CONF_DIR="${AGENT_SKELETON_CONFIG_DIR:-$HOME/.config/agent-skeleton}"
CONF="${NOTIFY_CONFIG:-$CONF_DIR/notify.env}"

say_line() { printf '%s\n' "$*"; }
ask() {  # ask "Question" default -> answer on stdout
  local q="$1" def="${2-}" ans
  if [ -n "$def" ]; then printf '%s [%s]: ' "$q" "$def" >&2; else printf '%s: ' "$q" >&2; fi
  IFS= read -r ans || ans=""
  [ -n "$ans" ] || ans="$def"
  printf '%s' "$ans"
}
yes_no() {  # yes_no "Question" y|n -> exit 0 for yes
  local ans
  ans="$(ask "$1 (y/n)" "$2")"
  case "$ans" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac
}
ask_secret() {  # ask_secret "Prompt" -> value on stdout, not echoed
  local v
  printf '%s (input hidden): ' "$1" >&2
  IFS= read -rs v || v=""
  printf '\n' >&2
  printf '%s' "$v"
}
get() { python3 "$ENVFILE" get --no-env "$CONF" "$1" 2>/dev/null || true; }
set_plain() { python3 "$ENVFILE" set "$CONF" "$1" --value "$2"; }
set_secret() { printf '%s' "$2" | python3 "$ENVFILE" set "$CONF" "$1"; }
tg() {  # tg METHOD -> Bot API JSON. The token goes to curl on stdin, inside a config.
  printf 'url = "https://api.telegram.org/bot%s/%s"\n' "$token" "$1" \
    | curl -sS --max-time 15 -K - 2>&1
}
json_field() {  # json_field 'python expression on d' < json
  python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(eval(sys.argv[1]) or "")
except Exception:
    print("")' "$1"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi
if [ "${1:-}" = "--show" ]; then
  if [ ! -f "$CONF" ]; then say_line "no config yet: $CONF"; exit 1; fi
  say_line "keys set in $CONF:"
  python3 "$ENVFILE" keys "$CONF" | sed 's/^/  /'
  python3 "$ENVFILE" check-mode "$CONF"
  exit $?
fi
if [ ! -t 0 ]; then
  say_line "notify-setup.sh is interactive: run it in a terminal (bin/skeleton setup voice)." >&2
  exit 2
fi
for cmd in python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || { say_line "missing $cmd" >&2; exit 1; }
done

umask 077
mkdir -p "$CONF_DIR" && chmod 700 "$CONF_DIR" 2>/dev/null
if [ ! -f "$CONF" ]; then
  printf '# agent-skeleton voice bundle. Secrets: keep this file at mode 0600, never in git.\n' > "$CONF"
  printf '# Every key can be overridden by an environment variable of the same name.\n' >> "$CONF"
fi
chmod 600 "$CONF"

say_line ""
say_line "🎧 Voice bundle setup. Config: $CONF"
say_line "   Channels: Telegram (voice bubbles with a speed control) and/or Google Chat."
say_line ""

channels=""

# --- 1. Telegram ----------------------------------------------------------------------
token="$(get TELEGRAM_BOT_TOKEN)"
default_tg=n
[ -n "$token" ] && default_tg=y
if yes_no "Use Telegram?" "$default_tg"; then
  if [ -n "$token" ] && yes_no "  A bot token is already stored. Keep it?" y; then
    :
  else
    say_line "  In Telegram, talk to @BotFather, send /newbot and copy the token it gives you."
    token="$(ask_secret "  Bot token")"
  fi
  me="$(tg getMe)"
  bot="$(printf '%s' "$me" | json_field 'd["result"]["username"] if d.get("ok") else ""')"
  if [ -z "$bot" ]; then
    say_line "  ❌ Telegram rejected that token; Telegram is skipped. Re-run setup to retry."
  else
    set_secret TELEGRAM_BOT_TOKEN "$token"
    say_line "  ✅ bot @$bot (token stored, ending ...${token: -4})"
    chat_id="$(get TELEGRAM_CHAT_ID)"
    if [ -z "$chat_id" ] || ! yes_no "  Keep chat id $chat_id?" y; then
      say_line "  Open Telegram, find @$bot, press START and send it any message."
      ask "  Press Enter when you have sent it" "" >/dev/null
      chat_id="$(tg getUpdates | json_field '[c for c in [(u.get(k) or {}).get("chat", {}).get("id") for u in d.get("result", []) for k in ("message", "edited_message", "channel_post")] if c][-1]')"
      if [ -z "$chat_id" ]; then
        chat_id="$(ask "  No message found yet. Type the chat id by hand, or Enter to skip" "")"
      fi
    fi
    if [ -n "$chat_id" ]; then
      set_plain TELEGRAM_CHAT_ID "$chat_id"
      say_line "  ✅ chat $chat_id"
      channels="telegram"
    fi
  fi
fi

# --- 2. Google Chat ---------------------------------------------------------------------
hook="$(get GCHAT_WEBHOOK_URL)"
space="$(get GCHAT_SPACE)"
default_chat=n
{ [ -n "$hook" ] || [ -n "$space" ]; } && default_chat=y
if yes_no "Use Google Chat?" "$default_chat"; then
  if [ -n "$hook" ] && yes_no "  A webhook URL is already stored. Keep it?" y; then
    :
  else
    say_line "  In the Chat space: Apps & integrations > Webhooks > Add webhook, copy the URL."
    hook="$(ask_secret "  Webhook URL (Enter to skip)")"
    case "$hook" in
      https://chat.googleapis.com/*) set_secret GCHAT_WEBHOOK_URL "$hook"; say_line "  ✅ webhook stored" ;;
      "") ;;
      *) say_line "  ❌ that does not look like a Chat webhook (https://chat.googleapis.com/...); skipped"; hook="" ;;
    esac
  fi
  say_line "  Audio in Chat needs the space id and the google bundle (gchat.py login)."
  space="$(ask "  Space for audio uploads, e.g. spaces/AAAA1234 (Enter to skip)" "$space")"
  case "$space" in
    spaces/*) set_plain GCHAT_SPACE "$space" ;;
    "") ;;
    *) say_line "  ❌ a space id starts with spaces/; skipped"; space="" ;;
  esac
  if [ -n "$hook" ] || [ -n "$space" ]; then
    channels="${channels:+$channels,}chat"
  fi
fi
set_plain NOTIFY_CHANNELS "${channels:-none}"

# --- 3. Text to speech ------------------------------------------------------------------
engine="$(get TTS_ENGINE)"
key_set="$(get TTS_API_KEY)"
say_line ""
if [ -n "$key_set" ] && yes_no "A Google TTS API key is stored. Keep using Google voices?" y; then
  engine=google
elif yes_no "Use Google Cloud TTS (Chirp 3 HD voices; needs a Google Cloud API key)?" n; then
  if /bin/bash "$here/tts-set-api-key.sh" --no-test; then
    engine=google
  else
    engine=""
  fi
fi
if [ "$engine" != google ]; then
  if command -v say >/dev/null 2>&1; then
    engine=say
    say_line "Using the built-in macOS voice (say). Free and offline."
  else
    engine=none
    say_line "No speech engine found: summaries will be sent as text."
  fi
fi
set_plain TTS_ENGINE "$engine"
if [ "$engine" != none ] && ! command -v ffmpeg >/dev/null 2>&1; then
  say_line "⚠️  ffmpeg is missing: brew install ffmpeg (audio conversion needs it)."
fi

# --- 4. Language, name, hub -------------------------------------------------------------
lang_default="$(get TTS_LANG)"
[ -n "$lang_default" ] || lang_default=en
lang="$(ask "Spoken language, en or es" "$lang_default")"
case "$lang" in en|es) set_plain TTS_LANG "$lang" ;; *) say_line "unsupported language $lang, keeping en"; set_plain TTS_LANG en ;; esac
name="$(ask "Your first name for the greeting (Enter for none)" "$(get VOICE_USER_NAME)")"
[ -n "$name" ] && set_plain VOICE_USER_NAME "$name"
hub_default=n
[ "$(get VOICE_HUB)" = on ] && hub_default=y
if yes_no "Also keep every note in the local voice hub (history + player, tools/voice-hub)?" "$hub_default"; then
  set_plain VOICE_HUB on
  say_line "  Start it with: tools/voice-hub/bin/avh serve   (or: tools/voice-hub/bin/avh service install)"
else
  set_plain VOICE_HUB off
fi

chmod 600 "$CONF"
say_line ""
say_line "Saved $CONF (0600). Keys set:"
python3 "$ENVFILE" keys "$CONF" | sed 's/^/  /'

# --- 5. Test, only with consent -----------------------------------------------------------
if [ "${channels:-none}" = none ] && [ "$(get VOICE_HUB)" != on ]; then
  say_line "No channel configured: nothing to test. The Stop hook stays inert until you add one."
  exit 0
fi
say_line ""
if yes_no "Send a test notification and a short test voice note now?" n; then
  /bin/bash "$here/notify.sh" --source NOTIFY ok "Channel ready" "The agent can reach you here." || true
  python3 "$here/voice-note.py" --source AGENT --title "Voice test" \
    "This is a test of the voice channel. From now on, long tasks end with a short spoken summary like this one." || true
fi
say_line "✅ voice setup done"
