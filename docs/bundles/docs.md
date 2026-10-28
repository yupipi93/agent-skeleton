# 📝 docs

On by default. Diagrams, print-ready PDFs and messages that survive a paste.

## Skills

| Skill | Use it for |
|---|---|
| `docs-mermaid-diagrams` | One palette, one shape vocabulary and label-safe characters for every Mermaid diagram; eight styled templates in `references/` |
| `docs-print-ready-pdf` | HTML that paginates cleanly in headless Chrome: the scale-to-fit and fixed-height traps, print CSS, contrast, page-count check |
| `docs-markdown-pdf-vscode` | The `yzane.markdown-pdf` extension: Chrome path, Mermaid 9.4.3 pin, page breaks, the editor engine-version mismatch |
| `chat-rich-message` | Copy-paste-ready messages for Teams, Google Chat, Slack, Gmail: a local HTML page with Copy rich and Copy plain buttons, built from a Markdown draft by `rich-message.py` |
| `docs-plan-to-docs` | **Command** (`/docs-plan-to-docs <plan>`): turn a finished `*.plan.md` into ADRs, guides, module READMEs and architecture docs, then delete the plan |

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/docs/scripts/chrome.sh` | `path`, `pdf IN OUT`, `screenshot IN OUT [W,H]` with headless Chrome and a throwaway profile; finds Chrome via `$CHROME_BIN`, `PATH` (Linux), the macOS app bundle, or snap |
| `kit/bundles/docs/scripts/open-local.sh` | Open a local file: `$BROWSER_OPEN_CMD`, else a tab in the editor's browser when run inside Cursor or VS Code (needs the extension below; `BROWSER_OPEN_TARGET=system` skips it), else `open` (macOS), `xdg-open` (Linux), `wslview` (WSL) |
| `kit/bundles/docs/scripts/rich-message.py` | Markdown draft to `chat-rich-message` page in one call: renders the template, runs the text guard and the em dash check, opens the page (about half a second) |
| `kit/bundles/docs/scripts/install-editor-browser.sh` | Package and install `editor-browser-open` (`kit/bundles/docs/editor-extension/`), a URI handler that opens a URL in Cursor's browser tab or VS Code's Simple Browser; also run by `bin/skeleton setup docs` |

```bash
kit/bundles/docs/scripts/chrome.sh pdf report.html report.pdf
kit/bundles/docs/scripts/open-local.sh local/messages/release-notes.html
kit/bundles/docs/scripts/rich-message.py local/messages/release-notes.md
```

## Dependencies

Google Chrome or Chromium for PDFs and screenshots (Homebrew cask `google-chrome`,
optional in the `Brewfile`); optional `node` to syntax-check page scripts.
