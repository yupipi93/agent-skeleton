#!/usr/bin/env bash
# Open a local file in the default browser or app, on macOS and Linux.
#
#   kit/bundles/docs/scripts/open-local.sh docs/messages.html
#   BROWSER_OPEN_CMD="open -a Firefox" kit/bundles/docs/scripts/open-local.sh page.html
#
# Uses $BROWSER_OPEN_CMD when set, else `open` (macOS), else `xdg-open` (Linux),
# else `wslview` (WSL). Returns immediately; the opener runs detached.
# Exit codes: 0 opened, 1 no opener found, 2 bad usage. bash 3.2 compatible.
set -u

if [ $# -ne 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
target="$1"
[ -e "$target" ] || { echo "open-local.sh: no such file: $target" >&2; exit 2; }

if [ -n "${BROWSER_OPEN_CMD:-}" ]; then
  # Intentionally word-split so "open -a Firefox" works.
  # shellcheck disable=SC2086
  $BROWSER_OPEN_CMD "$target" >/dev/null 2>&1 &
  exit 0
fi
if [ "$(uname -s)" = "Darwin" ] && command -v open >/dev/null 2>&1; then
  open "$target"
  exit $?
fi
for opener in xdg-open wslview; do
  if command -v "$opener" >/dev/null 2>&1; then
    "$opener" "$target" >/dev/null 2>&1 &
    exit 0
  fi
done
echo "open-local.sh: no opener found (set BROWSER_OPEN_CMD); open $target yourself" >&2
exit 1
