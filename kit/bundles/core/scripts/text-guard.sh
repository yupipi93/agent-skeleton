#!/usr/bin/env bash
#
# text-guard.sh: block outbound text that looks like it carries a secret.
#
# Generic gate for any bundle: ticket comments, PR bodies, chat messages, or the
# payload of a tool call when wired as a before_tool hook.
#
# Usage:
#   text-guard.sh --file draft.md               # check a file before sending it
#   printf '%s' "$text" | text-guard.sh         # check stdin
#   (as a hook) text-guard.sh --client claude   # stdin = the tool-call JSON payload
#
# Options:
#   --client <claude|cursor|gemini|antigravity>  emit that tool's "allow" JSON on success
#   --file PATH      read PATH instead of stdin
#   --em-dash        also block U+2014 (house style, see the style bundle)
#   --patterns PATH  pattern file (default: lib/secret-patterns.txt next to this script)
#
# Exit codes: 0 clean, 2 blocked (reason on stderr, label only, never the match),
# 64 usage error. A missing pattern file blocks (fail closed).
#
# bash 3.2 compatible, no dependencies beyond grep.

set -u

here="$(cd "$(dirname "$0")" && pwd)"
patterns="${TEXT_GUARD_PATTERNS:-$here/lib/secret-patterns.txt}"
client=""
file=""
em_dash=0

usage() { sed -n '3,22p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --client)
      [ $# -ge 2 ] || { echo "text-guard: --client needs a value" >&2; exit 64; }
      client="$2"; shift 2 ;;
    --client=*) client="${1#*=}"; shift ;;
    --file)
      [ $# -ge 2 ] || { echo "text-guard: --file needs a path" >&2; exit 64; }
      file="$2"; shift 2 ;;
    --file=*) file="${1#*=}"; shift ;;
    --patterns)
      [ $# -ge 2 ] || { echo "text-guard: --patterns needs a path" >&2; exit 64; }
      patterns="$2"; shift 2 ;;
    --em-dash) em_dash=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "text-guard: unknown argument: $1" >&2; exit 64 ;;
  esac
done

block() {
  local reason="$1"
  local msg="text-guard: blocked, $reason. Reference secrets by name or location, never by value."
  if [ "$client" = "cursor" ]; then
    printf '{"permission":"deny","user_message":"%s","agent_message":"%s"}\n' "$msg" "$msg"
  fi
  echo "$msg" >&2
  exit 2
}

allow() {
  case "$client" in
    cursor) printf '{"permission":"allow"}\n' ;;
    gemini) printf '{"decision":"allow"}\n' ;;
  esac
  exit 0
}

if [ ! -r "$patterns" ]; then
  block "pattern file not readable ($patterns)"
fi

if [ -n "$file" ]; then
  [ -r "$file" ] || { echo "text-guard: cannot read $file" >&2; exit 64; }
  content="$(cat "$file")"
else
  content="$(cat)"
fi

[ -n "$content" ] || allow

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|\#*) continue ;; esac
  label="${line%%[[:space:]]*}"
  regex="${line#"$label"}"
  regex="${regex#"${regex%%[![:space:]]*}"}"
  [ -n "$regex" ] || continue
  if printf '%s\n' "$content" | grep -E -q -e "$regex" 2>/dev/null; then
    block "possible secret ($label)"
  fi
done < "$patterns"

if [ "$em_dash" -eq 1 ]; then
  dash="$(printf '\342\200\224')"
  case "$content" in
    *"$dash"*) block "em dash (U+2014) found; use a comma, colon, parentheses or '-'" ;;
  esac
fi

allow
