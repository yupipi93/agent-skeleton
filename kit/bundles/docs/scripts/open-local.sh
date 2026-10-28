#!/usr/bin/env bash
# Open a local file in the editor's browser, the default browser or app, on macOS and Linux.
#
#   kit/bundles/docs/scripts/open-local.sh docs/messages.html
#   BROWSER_OPEN_CMD="open -a Firefox" kit/bundles/docs/scripts/open-local.sh page.html
#   BROWSER_OPEN_TARGET=system kit/bundles/docs/scripts/open-local.sh page.html
#
# Order: $BROWSER_OPEN_CMD when set; else, when running inside Cursor or VS Code with the
# editor-browser-open extension installed (install-editor-browser.sh), a tab in the
# editor's own browser; else `open` (macOS), `xdg-open` (Linux) or `wslview` (WSL).
# BROWSER_OPEN_TARGET=system skips the editor, =editor fails instead of falling back.
# Returns immediately. Exit codes: 0 opened, 1 no opener found, 2 bad usage. bash 3.2.
set -u

if [ $# -ne 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
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

# The editor we run under, from the variables its terminals and extension hosts set.
editor_scheme() {
  case "${VSCODE_IPC_HOOK:-}${VSCODE_IPC_HOOK_CLI:-}${VSCODE_GIT_ASKPASS_MAIN:-}" in
    *[Cc]ursor*) echo cursor; return ;;
  esac
  if [ -n "${CURSOR_TRACE_ID:-}${CURSOR_SPAWN_CHAIN:-}" ]; then echo cursor; return; fi
  if [ "${TERM_PROGRAM:-}" = "vscode" ] || [ -n "${VSCODE_IPC_HOOK:-}${VSCODE_PID:-}" ]; then
    echo vscode
  fi
}

open_in_editor() {
  local scheme dir url
  scheme=$(editor_scheme)
  [ -n "$scheme" ] || return 1
  [ "$scheme" = cursor ] && dir="$HOME/.cursor/extensions" || dir="$HOME/.vscode/extensions"
  ls -d "$dir"/agent-skeleton.editor-browser-open-* >/dev/null 2>&1 || return 1
  url=$(python3 -c 'import os,sys,urllib.parse as u; print(u.quote(u.urljoin("file:", u.quote(os.path.abspath(sys.argv[1]))), safe=""))' "$target") || return 1
  url="$scheme://agent-skeleton.editor-browser-open/open?url=$url"
  if [ "$(uname -s)" = "Darwin" ]; then
    open "$url"
  else
    xdg-open "$url" >/dev/null 2>&1 &
  fi
}

case "${BROWSER_OPEN_TARGET:-auto}" in
  system) ;;
  editor)
    open_in_editor && exit 0
    echo "open-local.sh: not inside Cursor/VS Code or extension missing (install-editor-browser.sh)" >&2
    exit 1 ;;
  *) open_in_editor && exit 0 ;;
esac

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
