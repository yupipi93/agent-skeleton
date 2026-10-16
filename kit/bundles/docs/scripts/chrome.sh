#!/usr/bin/env bash
# Find headless Chrome and use it for print-ready PDFs and screenshots.
#
#   kit/bundles/docs/scripts/chrome.sh path
#   kit/bundles/docs/scripts/chrome.sh pdf IN.html OUT.pdf
#   kit/bundles/docs/scripts/chrome.sh screenshot IN.html OUT.png [WIDTH,HEIGHT]
#
# Lookup order: $CHROME_BIN, then google-chrome, google-chrome-stable, chromium,
# chromium-browser, chrome on PATH, then the macOS app bundles
# (/Applications/Google Chrome.app/Contents/MacOS/Google Chrome, Chromium, Canary,
# and the same under ~/Applications), then /snap/bin/chromium.
#
# Exit codes: 0 ok, 1 Chrome not found, 2 bad usage, 3 conversion produced nothing.
# Each run uses a throwaway profile directory, so it never touches your browser
# profile. bash 3.2 compatible.
set -u

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
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

run_headless() {
  # $1 chrome binary, rest: extra flags then the URL
  local chrome="$1"
  shift
  local profile
  profile=$(mktemp -d "${TMPDIR:-/tmp}/chrome-profile.XXXXXX") || return 1
  "$chrome" --headless=new --disable-gpu --no-first-run --no-default-browser-check \
    --disable-extensions --user-data-dir="$profile" \
    --run-all-compositor-stages-before-draw --virtual-time-budget=6000 \
    "$@" >/dev/null 2>&1
  local rc=$?
  rm -rf "$profile"
  return $rc
}

cmd="${1:-}"
case "$cmd" in
  path)
    find_chrome
    ;;
  pdf)
    [ $# -eq 3 ] || usage
    [ -f "$2" ] || { echo "chrome.sh: no such file: $2" >&2; exit 2; }
    chrome=$(find_chrome) || exit 1
    url=$(file_url "$2") || exit 2
    rm -f "$3"
    run_headless "$chrome" --no-pdf-header-footer --print-to-pdf="$3" "$url"
    [ -s "$3" ] || { echo "chrome.sh: PDF conversion produced nothing" >&2; exit 3; }
    echo "pdf $3"
    ;;
  screenshot)
    [ $# -ge 3 ] && [ $# -le 4 ] || usage
    [ -f "$2" ] || { echo "chrome.sh: no such file: $2" >&2; exit 2; }
    chrome=$(find_chrome) || exit 1
    url=$(file_url "$2") || exit 2
    size="${4:-1080,1400}"
    rm -f "$3"
    run_headless "$chrome" --hide-scrollbars --window-size="$size" --screenshot="$3" "$url"
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
