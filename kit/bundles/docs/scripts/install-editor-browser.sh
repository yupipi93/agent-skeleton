#!/usr/bin/env bash
# Install the editor-browser-open extension into Cursor and/or VS Code.
#
#   kit/bundles/docs/scripts/install-editor-browser.sh
#
# The extension (kit/bundles/docs/editor-extension/) lets open-local.sh show a page in
# the editor's own browser instead of a new system browser window. It is packaged as a
# .vsix with python3 (no vsce or npm needed) and installed with each editor CLI found
# (`cursor`, `code`). Re-running it reinstalls; it is idempotent.
# Exit codes: 0 installed in at least one editor, 1 no editor CLI found.
# bash 3.2 compatible.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$here/../editor-extension"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
vsix="$work/editor-browser-open.vsix"

python3 - "$src" "$vsix" <<'PY'
import json, sys, zipfile
from pathlib import Path
src, out = Path(sys.argv[1]), sys.argv[2]
pkg = json.loads((src / "package.json").read_text())
manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{pkg['name']}" Version="{pkg['version']}" Publisher="{pkg['publisher']}"/>
    <DisplayName>{pkg['displayName']}</DisplayName>
    <Description xml:space="preserve">{pkg['description']}</Description>
    <Categories>Other</Categories>
    <Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="{pkg['engines']['vscode']}"/></Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets>
</PackageManifest>
"""
types = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", types)
    z.writestr("extension.vsixmanifest", manifest)
    for f in ("package.json", "extension.js"):
        z.write(src / f, f"extension/{f}")
PY
[ -s "$vsix" ] || { echo "install-editor-browser.sh: packaging failed" >&2; exit 1; }

# Editor CLIs inside the app bundles first: on PATH, `cursor` may be the Cursor Agent
# CLI, which cannot install extensions.
found=0
installed=0
for cli in \
  "$HOME/Applications/Cursor.app/Contents/Resources/app/bin/cursor" \
  "/Applications/Cursor.app/Contents/Resources/app/bin/cursor" \
  "$HOME/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
  "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" \
  "$(command -v code 2>/dev/null)"; do
  [ -n "$cli" ] && [ -x "$cli" ] || continue
  found=1
  if out=$("$cli" --install-extension "$vsix" --force 2>&1); then
    echo "✅ $cli: agent-skeleton.editor-browser-open installed"
    installed=1
  else
    echo "⚠️ $cli: install failed: $out" >&2
  fi
done
[ "$found" = 1 ] || { echo "install-editor-browser.sh: no Cursor or VS Code installation found" >&2; exit 1; }
[ "$installed" = 1 ] || exit 1
echo "Reload open editor windows once (Developer: Reload Window) if a URI is not picked up."
