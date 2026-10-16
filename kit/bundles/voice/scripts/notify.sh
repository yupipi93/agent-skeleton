#!/bin/bash
# notify.sh: send a text notification to the channels in ~/.config/agent-skeleton/notify.env
#
#   notify.sh [--source TAG] [--code CMD | --code-only CMD] [--to CHANNELS] [--dry-run]
#             [--quiet] <info|ok|warn|crit> <title> <message...>
#   notify.sh --code-only CMD          # just the command, as its own message
#   notify.sh --test                   # formatting showcase, to verify a channel
#
# Channels: Telegram (bot) and Google Chat (incoming webhook, or a space through the
# google bundle's gchat.py). Levels: info and ok arrive silently, warn and crit notify.
# Title and message may use inline HTML (<b> <i> <s> <code>); it is converted per channel.
#
# Every command sent with --code / --code-only is also printed on stderr as a fenced
# block: a command the user must run goes to the channel AND into the agent's reply.
#
# With no channel configured this is a silent no-op that exits 0: an emitter must never
# break because a token is missing. Exit codes: 0 sent, 3 partial, 1 nothing delivered.
#
# The work happens in lib/notifylib.py (shared with voice-note.py), so secrets stay
# inside one Python process: never on a command line, never in a log. bash 3.2 friendly.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  printf 'notify.sh: python3 is required\n' >&2
  exit 1
fi
exec python3 "$here/lib/notifylib.py" notify "$@"
