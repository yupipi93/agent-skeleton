#!/bin/bash
# setup.sh: connect the docs bundle to your editor (bin/skeleton setup docs).
#
# Installs the editor-browser-open extension into Cursor and/or VS Code, so
# open-local.sh and rich-message.py show pages in the editor's own browser.
# bash 3.2 compatible.
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$here/scripts/install-editor-browser.sh"
