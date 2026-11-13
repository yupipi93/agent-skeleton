#!/usr/bin/env bash
# Find headless Chrome and use it for print-ready PDFs and screenshots.
#
#   kit/bundles/docs/scripts/chrome.sh path
#   kit/bundles/docs/scripts/chrome.sh pdf IN.html OUT.pdf
#   kit/bundles/docs/scripts/chrome.sh screenshot IN.html OUT.png [WIDTH,HEIGHT]
#
# IN is a local file or an http(s):// or file:// URL.
#
# Lookup order: $CHROME_BIN, then google-chrome, google-chrome-stable, chromium,
# chromium-browser, chrome on PATH, then the macOS app bundles
# (/Applications/Google Chrome.app/Contents/MacOS/Google Chrome, Chromium, Canary,
# and the same under ~/Applications), then /snap/bin/chromium.
#
# Environment:
#   CHROME_TIMEOUT=90               hard limit in seconds; Chrome is killed after it
#   CHROME_VIRTUAL_TIME_BUDGET=6000 ms of page time before the capture
#   CHROME_HIDE_SCROLLBARS=1        0 keeps scrollbars in screenshots
#   CHROME_EXTRA_FLAGS="..."        more Chrome flags, split on spaces
#
# Exit codes: 0 ok, 1 Chrome not found, 2 bad usage, 3 conversion produced nothing,
# 4 timed out. Each run uses a throwaway profile directory, so it never touches your
# browser profile. Chrome and the profile are removed on every exit path (success,
# failure, timeout, Ctrl-C, SIGTERM, SIGHUP). bash 3.2 compatible.
set -u

usage() {
  sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

find_chrome() {
  if [ -n "${CHROME_BIN:-}" ]; then
    if [ -x "$CHROME_BIN" ] || command -v "$CHROME_BIN" >/dev/null 2>&1; then
      printf '%s\n' "$CHROME_BIN"
      return 0
    fi
    echo "chrome.sh: CHROME_BIN=$CHROME_BIN is not executable" >&2
    return 1
  fi
  for name in google-chrome google-chrome-stable chromium chromium-browser chrome; do
    if command -v "$name" >/dev/null 2>&1; then
      command -v "$name"
      return 0
    fi
  done
  for app in \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary" \
    "$HOME/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "$HOME/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "/snap/bin/chromium"; do
    if [ -x "$app" ]; then
      printf '%s\n' "$app"
      return 0
    fi
  done
  echo "chrome.sh: no Chrome or Chromium found; install one or set CHROME_BIN" >&2
  return 1
}

file_url() {
  # Absolute file:// URL for a local path (spaces escaped).
  local dir base
  dir=$(cd "$(dirname "$1")" && pwd) || return 1
  base=$(basename "$1")
  printf 'file://%s/%s\n' "$dir" "$base" | sed 's/ /%20/g'
}

input_url() {
  # URL for IN: URLs pass through, local files become file:// URLs.
  case "$1" in
    http://*|https://*|file://*) printf '%s\n' "$1"; return 0 ;;
  esac
  [ -f "$1" ] || { echo "chrome.sh: no such file: $1" >&2; return 1; }
  file_url "$1"
}

# State shared with the cleanup trap.
CHROME_PID=""
WATCHDOG_PID=""
PROFILE_DIR=""
TIMED_OUT_FLAG=""

cleanup() {
  # Stop the watchdog, then Chrome's whole process group, then remove the profile.
  # Safe to call more than once.
  if [ -n "$WATCHDOG_PID" ]; then
    kill -- "-$WATCHDOG_PID" 2>/dev/null || kill "$WATCHDOG_PID" 2>/dev/null
    WATCHDOG_PID=""
  fi
  if [ -n "$CHROME_PID" ]; then
    if kill -0 "$CHROME_PID" 2>/dev/null; then
      kill -TERM -- "-$CHROME_PID" 2>/dev/null || kill -TERM "$CHROME_PID" 2>/dev/null
      local i=0
      while [ $i -lt 20 ] && kill -0 "$CHROME_PID" 2>/dev/null; do
        sleep 0.1
        i=$((i + 1))
      done
    fi
    # The group may outlive its leader (helpers): always send the final KILL.
    kill -KILL -- "-$CHROME_PID" 2>/dev/null
    kill -KILL "$CHROME_PID" 2>/dev/null
    wait "$CHROME_PID" 2>/dev/null
    CHROME_PID=""
  fi
  if [ -n "$PROFILE_DIR" ]; then
    rm -rf "$PROFILE_DIR"
    PROFILE_DIR=""
  fi
  if [ -n "$TIMED_OUT_FLAG" ]; then
    rm -f "$TIMED_OUT_FLAG"
    TIMED_OUT_FLAG=""
  fi
}

trap cleanup EXIT
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM
trap 'cleanup; exit 129' HUP

run_headless() {
  # $1 chrome binary, rest: extra flags then the URL. Returns Chrome's status, 4 on timeout.
  local chrome="$1"
  shift
  local limit="${CHROME_TIMEOUT:-90}"
  case "$limit" in ''|*[!0-9]*) echo "chrome.sh: CHROME_TIMEOUT must be whole seconds" >&2; return 2 ;; esac
  local budget="${CHROME_VIRTUAL_TIME_BUDGET:-6000}"
  PROFILE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/chrome-profile.XXXXXX") || return 1
  TIMED_OUT_FLAG="$PROFILE_DIR.timedout"
  # Job control gives the background Chrome its own process group, so cleanup can
  # signal Chrome and every helper it started with one group kill.
  set -m
  # shellcheck disable=SC2086  # CHROME_EXTRA_FLAGS is split on purpose
  "$chrome" --headless=new --disable-gpu --no-first-run --no-default-browser-check \
    --disable-extensions --user-data-dir="$PROFILE_DIR" \
    --run-all-compositor-stages-before-draw --virtual-time-budget="$budget" \
    ${CHROME_EXTRA_FLAGS:-} "$@" >/dev/null 2>&1 </dev/null &
  CHROME_PID=$!
  # Watchdog: one-second naps so killing it never leaves a long sleep behind.
  (
    n=0
    while [ $n -lt "$limit" ]; do
      if ! kill -0 "$CHROME_PID" 2>/dev/null; then
        # Chrome is done. If this script was SIGKILLed meanwhile, its cleanup never ran.
        # A zombie (killed, not yet reaped by its parent) still answers kill -0.
        case "$(ps -o stat= -p $$ 2>/dev/null)" in
          ''|Z*) rm -rf "$PROFILE_DIR" "$TIMED_OUT_FLAG" ;;
        esac
        exit 0
      fi
      sleep 1
      n=$((n + 1))
    done
    : >"$TIMED_OUT_FLAG"
    kill -TERM -- "-$CHROME_PID" 2>/dev/null || kill -TERM "$CHROME_PID" 2>/dev/null
    sleep 3
    kill -KILL -- "-$CHROME_PID" 2>/dev/null || kill -KILL "$CHROME_PID" 2>/dev/null
    # If this script itself was SIGKILLed, nobody else will clean up.
    if ! kill -0 $$ 2>/dev/null; then
      rm -rf "$PROFILE_DIR" "$TIMED_OUT_FLAG"
    fi
  ) >/dev/null 2>&1 </dev/null &
  WATCHDOG_PID=$!
  set +m
  wait "$CHROME_PID"
  local rc=$?
  local timed_out=0
  [ -e "$TIMED_OUT_FLAG" ] && timed_out=1
  cleanup
  if [ $timed_out -eq 1 ]; then
    echo "chrome.sh: Chrome did not finish within ${limit}s; killed (CHROME_TIMEOUT)" >&2
    return 4
  fi
  return $rc
}

cmd="${1:-}"
case "$cmd" in
  path)
    find_chrome
    ;;
  pdf)
    [ $# -eq 3 ] || usage
    url=$(input_url "$2") || exit 2
    chrome=$(find_chrome) || exit 1
    rm -f "$3"
    run_headless "$chrome" --no-pdf-header-footer --print-to-pdf="$3" "$url"
    [ $? -eq 4 ] && exit 4
    [ -s "$3" ] || { echo "chrome.sh: PDF conversion produced nothing" >&2; exit 3; }
    echo "pdf $3"
    ;;
  screenshot)
    [ $# -ge 3 ] && [ $# -le 4 ] || usage
    url=$(input_url "$2") || exit 2
    chrome=$(find_chrome) || exit 1
    size="${4:-1080,1400}"
    hide="--hide-scrollbars"
    [ "${CHROME_HIDE_SCROLLBARS:-1}" = "0" ] && hide=""
    rm -f "$3"
    # shellcheck disable=SC2086  # empty $hide must vanish
    run_headless "$chrome" $hide --window-size="$size" --screenshot="$3" "$url"
    [ $? -eq 4 ] && exit 4
    [ -s "$3" ] || { echo "chrome.sh: screenshot produced nothing" >&2; exit 3; }
    echo "png $3"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "chrome.sh: unknown command: $cmd" >&2
    usage
    ;;
esac
