#!/usr/bin/env bash
#
# auto-accept-install.sh: install the AI Auto-Accept extension in VS Code-family editors.
#
# VS Code installs it from the Visual Studio Marketplace. Cursor, Windsurf and VSCodium
# use the Open VSX registry, which does not list it, so the script downloads the VSIX
# from the Marketplace and installs that file. Turning the Claude Code hook on stays a
# step in the editor (it writes the hook into ~/.claude/settings.json); the script
# prints it at the end.
#
# Usage:
#   auto-accept-install.sh                  # every editor CLI found on PATH
#   auto-accept-install.sh --editor cursor  # one editor: code, cursor, windsurf, codium
#   auto-accept-install.sh --dry-run        # print the commands only
#
# Environment:
#   AUTO_ACCEPT_EDITORS  space-separated editor CLIs (default: code cursor windsurf codium)
#   AUTO_ACCEPT_VSIX_URL VSIX download URL (default: the Marketplace "latest" package)
#
# Exit codes: 0 installed (or nothing to do), 1 an install failed, 64 usage error.
# bash 3.2 compatible; needs curl only for non-Marketplace editors.

set -u

EXT_ID="devcloudops.ai-auto-accept"
VSIX_URL="${AUTO_ACCEPT_VSIX_URL:-https://marketplace.visualstudio.com/_apis/public/gallery/publishers/DevCloudOps/vsextensions/ai-auto-accept/latest/vspackage}"
editors="${AUTO_ACCEPT_EDITORS:-code cursor windsurf codium}"
dry=0

while [ $# -gt 0 ]; do
  case "$1" in
    --editor) [ $# -ge 2 ] || { echo "error: --editor needs a name" >&2; exit 64; }; editors="$2"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -h|--help) awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; exit 0 ;;
    *) echo "error: unknown argument $1" >&2; exit 64 ;;
  esac
done

run() {
  echo "+ $*"
  [ "$dry" -eq 1 ] || "$@"
}

vsix=""
fetch_vsix() {
  [ -n "$vsix" ] && return 0
  command -v curl >/dev/null 2>&1 || { echo "error: curl not found, needed to download the VSIX" >&2; return 1; }
  tmp="$(mktemp -d)"
  vsix="$tmp/ai-auto-accept.vsix"
  run curl -fsSL --compressed -o "$vsix" "$VSIX_URL" || { vsix=""; return 1; }
}

found=0
failed=0
for ed in $editors; do
  command -v "$ed" >/dev/null 2>&1 || continue
  found=1
  echo "== $ed"
  if [ "$ed" = "code" ]; then
    run "$ed" --install-extension "$EXT_ID" --force || failed=1
  else
    if fetch_vsix; then
      run "$ed" --install-extension "$vsix" --force || failed=1
    else
      failed=1
    fi
  fi
done

if [ "$found" -eq 0 ]; then
  echo "No editor CLI found ($editors). In VS Code or Cursor run the Command Palette" >&2
  echo "command 'Shell Command: Install ... command in PATH', then run this again." >&2
  exit 1
fi

cat <<'EOF'

Next, in each editor:
  1. Optional: stricter deny-list for the kit's safety gates. Paste the output of
       kit/bundles/core/scripts/auto-accept-audit.py --print-settings
     into User settings (JSON). Without it the extension's built-in list applies.
  2. Command Palette > "AI Auto-Accept: Set Up Chat Auto-Approve" > Recommended.
  3. Open a new Claude Code chat; the status bar shows "Auto-Accept".
Check any time with kit/bundles/core/scripts/auto-accept-audit.py
EOF
exit "$failed"
