#!/bin/bash
# notify-setup.sh: interactive setup of the voice bundle (bin/skeleton setup voice).
#
#   kit/bundles/voice/scripts/notify-setup.sh          # the wizard
#   kit/bundles/voice/scripts/notify-setup.sh --show   # which keys are set (never values)
#
# Writes ~/.config/agent-skeleton/notify.env (mode 0600, directory 0700). The default path
# keeps every note on this machine:
#   1. The local voice hub (tools/voice-hub): notes are stored there and played in its web
#      player. It offers to install and start the hub as a login service (macOS).
#   2. Text to speech: the macOS `say` voice, or Google Cloud TTS if you give an API key.
#   3. Language and your first name for the greeting.
#   4. Advanced, optional, only if you choose it: Telegram and/or Google Chat delivery.
#   5. A test voice note to the hub, only if you say yes.
#
# Secrets are read with a hidden prompt, reach curl through a config on stdin (`curl -K -`)
# and are stored with envfile.py on stdin: never on a command line, never echoed back.
# bash 3.2 compatible.
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../../.." && pwd)"
ENVFILE="$root/kit/bundles/core/scripts/lib/envfile.py"
HUB="$root/tools/voice-hub/bin/avh"
HUB_CMD="tools/voice-hub/bin/avh"
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
hub_running() { python3 "$HUB" ping >/dev/null 2>&1; }

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
command -v python3 >/dev/null 2>&1 || { say_line "missing python3" >&2; exit 1; }

umask 077
mkdir -p "$CONF_DIR" && chmod 700 "$CONF_DIR" 2>/dev/null
if [ ! -f "$CONF" ]; then
  printf '# agent-skeleton voice bundle. Secrets: keep this file at mode 0600, never in git.\n' > "$CONF"
  printf '# Every key can be overridden by an environment variable of the same name.\n' >> "$CONF"
fi
chmod 600 "$CONF"

say_line ""
say_line "🎧 Voice bundle setup. Config: $CONF"
say_line "   Voice notes go to the local voice hub, a web player on this machine."
say_line "   Telegram and Google Chat are optional extras, offered at the end."
say_line ""

# --- 1. The local voice hub -------------------------------------------------------------
say_line "1. Local voice hub ($HUB_CMD)"
set_plain VOICE_HUB on
if ! command -v ffmpeg >/dev/null 2>&1; then
  say_line "  ⚠️  ffmpeg is missing: brew install ffmpeg (the hub and the voices need it)."
fi
if hub_running; then
  say_line "  ✅ $(python3 "$HUB" ping 2>/dev/null)"
elif [ "$(uname -s)" = Darwin ]; then
  if yes_no "  The hub is not running. Install and start it as a login service now (launchd)?" y; then
    python3 "$HUB" service install || say_line "  ❌ service install failed; run it again: $HUB_CMD service install"
    i=0
    while [ "$i" -lt 20 ] && ! hub_running; do sleep 0.5; i=$((i + 1)); done
    if hub_running; then
      say_line "  ✅ $(python3 "$HUB" ping 2>/dev/null)"
    else
      say_line "  ❌ the hub did not answer yet; check it with: $HUB_CMD doctor"
    fi
  else
    say_line "  Start it later with: $HUB_CMD service install   (or in the foreground: $HUB_CMD serve)"
  fi
else
  say_line "  The hub is not running. Start it with: $HUB_CMD serve"
  say_line "  (keep it running with your own supervisor: a systemd user unit, tmux, ...)"
fi
open_default="$(get VOICE_HUB_OPEN)"
[ -n "$open_default" ] || open_default=auto
say_line "  When a note arrives: auto plays it in an open hub tab, else opens the player in"
say_line "  your browser; always opens the browser; never only prints the link."
open_mode="$(ask "  Play mode, auto, always or never" "$open_default")"
case "$open_mode" in
  auto|always|never) set_plain VOICE_HUB_OPEN "$open_mode" ;;
  *) say_line "  unknown mode, keeping auto"; set_plain VOICE_HUB_OPEN auto ;;
esac

# --- 2. Text to speech ------------------------------------------------------------------
engine="$(get TTS_ENGINE)"
key_set="$(get TTS_API_KEY)"
say_line ""
say_line "2. Voice"
if [ -n "$key_set" ] && yes_no "  A Google TTS API key is stored. Keep using Google voices?" y; then
  engine=google
elif yes_no "  Use Google Cloud TTS (Chirp 3 HD voices; needs a Google Cloud API key)?" n; then
  if /bin/bash "$here/tts-set-api-key.sh" --no-test; then
    engine=google
  else
    engine=""
  fi
fi
if [ "$engine" != google ]; then
  if command -v say >/dev/null 2>&1; then
    engine=say
    say_line "  Using the built-in macOS voice (say). Free and offline."
  else
    engine=none
    say_line "  ⚠️  No speech engine found (no macOS say, no Google key). The hub stores audio"
    say_line "     only, so add a key later: kit/bundles/voice/scripts/tts-set-api-key.sh"
  fi
fi
set_plain TTS_ENGINE "$engine"

# --- 3. Language and name ---------------------------------------------------------------
say_line ""
say_line "3. Language and greeting"
lang_default="$(get TTS_LANG)"
[ -n "$lang_default" ] || lang_default=en
lang="$(ask "  Spoken language, en or es" "$lang_default")"
case "$lang" in
  en|es) set_plain TTS_LANG "$lang" ;;
  *) say_line "  unsupported language $lang, keeping en"; set_plain TTS_LANG en ;;
esac
name="$(ask "  Your first name for the greeting (Enter for none)" "$(get VOICE_USER_NAME)")"
[ -n "$name" ] && set_plain VOICE_USER_NAME "$name"

# --- 4. Advanced, optional: external channels -------------------------------------------
setup_telegram() {
  command -v curl >/dev/null 2>&1 || { say_line "  missing curl: Telegram skipped"; return 1; }
  token="$(get TELEGRAM_BOT_TOKEN)"
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
    return 1
  fi
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
  [ -n "$chat_id" ] || return 1
  set_plain TELEGRAM_CHAT_ID "$chat_id"
  say_line "  ✅ chat $chat_id"
  return 0
}

setup_chat() {
  hook="$(get GCHAT_WEBHOOK_URL)"
  space="$(get GCHAT_SPACE)"
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
  [ -n "$hook" ] || [ -n "$space" ]
}

say_line ""
say_line "4. Advanced, optional: Telegram and Google Chat"
say_line "   Off unless you choose them here. Notes then leave this machine, so pick only"
say_line "   channels you trust with your work content."
external=""
current="$(get NOTIFY_CHANNELS)"
ext_default=n
case ",$current," in *,telegram,*|*,chat,*) ext_default=y ;; esac
if yes_no "Also deliver voice notes and notifications to Telegram or Google Chat?" "$ext_default"; then
  tg_default=n
  case ",$current," in *,telegram,*) tg_default=y ;; esac
  if yes_no "  Use Telegram?" "$tg_default" && setup_telegram; then
    external="telegram"
  fi
  chat_default=n
  case ",$current," in *,chat,*) chat_default=y ;; esac
  if yes_no "  Use Google Chat?" "$chat_default" && setup_chat; then
    external="${external:+$external,}chat"
  fi
fi
set_plain NOTIFY_CHANNELS "hub${external:+,$external}"

chmod 600 "$CONF"
say_line ""
say_line "Saved $CONF (0600). Channels: hub${external:+,$external}. Keys set:"
python3 "$ENVFILE" keys "$CONF" | sed 's/^/  /'

# --- 5. Test, only with consent -----------------------------------------------------------
say_line ""
if [ "$engine" != none ] && yes_no "Send a short test voice note to the hub now?" n; then
  if hub_running; then
    python3 "$here/voice-note.py" --to hub --source AGENT --title "Voice test" \
      "This is a test of the voice hub. From now on, long tasks end with a short spoken summary like this one." || true
  else
    say_line "  The hub is not running, so the test is skipped. Start it: $HUB_CMD service install (macOS) or $HUB_CMD serve"
  fi
fi
if [ -n "$external" ] && yes_no "Send a test text notification to $external now?" n; then
  /bin/bash "$here/notify.sh" --to "$external" --source NOTIFY ok "Channel ready" "The agent can reach you here." || true
fi
say_line "✅ voice setup done"
