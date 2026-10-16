---
name: docs-markdown-pdf-vscode
description: "Configure and troubleshoot the yzane.markdown-pdf extension for VS Code and Cursor (Markdown to PDF, HTML, PNG, JPEG with Mermaid): Chrome path, mermaid pin, page breaks, engine-version mismatch. Use when markdown-pdf fails, Mermaid does not render in a PDF, or the extension says it is incompatible."
---

# Markdown to PDF in VS Code and Cursor (yzane.markdown-pdf)

Extension: [yzane.markdown-pdf](https://github.com/yzane/vscode-markdown-pdf). It
converts Markdown to PDF, HTML, PNG or JPEG inside VS Code or Cursor through a
headless Chromium (Puppeteer).

Version facts below were true when this skill was written. **Verify current versions
before acting on them**: check the extension's changelog and your editor's engine
version (Help, About).

## Install

Marketplace (VS Code) or Open VSX (Cursor): `yzane.markdown-pdf`.

On first use it downloads Chromium (about 170 to 280 MB). To skip that, point it at
the Chrome you already have:

```json
{
  "markdown-pdf.executablePath": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
}
```

On Linux use the output of `kit/bundles/docs/scripts/chrome.sh path` (for example
`/usr/bin/google-chrome`).

## "Extension is not compatible with Code 1.x"

Cursor ships an older VS Code engine than the newest extension builds target. When
the extension raised its required engine (v2.0.0 requires `^1.110.0`), Cursor builds
on an older engine refused to activate it:

```
Extension is not compatible with Code 1.105.1. Extension requires: ^1.110.0.
```

A machine where it "still works" simply has an older extension version. Fix: install
the last version whose engine requirement your editor meets (at the time of writing
**v1.5.0**, engine `^1.0.0`):

```bash
curl -fL -o ~/Downloads/markdown-pdf-1.5.0.vsix \
  "https://open-vsx.org/api/yzane/markdown-pdf/1.5.0/file/yzane.markdown-pdf-1.5.0.vsix"
cursor --uninstall-extension yzane.markdown-pdf
cursor --install-extension ~/Downloads/markdown-pdf-1.5.0.vsix --force
```

Reload the window (Command Palette, *Developer: Reload Window*).

Auto-update will bump it back to an incompatible build. While *Auto Update All (From
Publisher)* is on, the per-extension toggle is greyed out, so disable auto-update
globally in user `settings.json` and update extensions by hand:

```json
{ "extensions.autoUpdate": false }
```

Check the installed version's engine requirement:

```bash
grep -o '"vscode"[^,}]*' ~/.cursor/extensions/yzane.markdown-pdf-*/package.json
```

## Usage

Open a `.md` file, Command Palette, `markdown-pdf: Export (pdf)` (or html, png, jpeg).

## Mermaid

The default Mermaid URL often fails or loads an incompatible version. The extension
initialises Mermaid with the v9 API, so **pin Mermaid 9.4.3** in the **workspace**
settings (`.vscode/settings.json`; it is unreliable from user settings):

```json
{
  "markdown-pdf.mermaidServer": "https://unpkg.com/mermaid@9.4.3/dist/mermaid.min.js"
}
```

Mermaid 9.4.3 is older than what GitHub renders, so labels must follow the safe
character rules in skill `docs-mermaid-diagrams` (section 5.1).

| Symptom | Cause | Fix |
|---|---|---|
| Diagram shows as a code block | Mermaid JS did not load | Set `markdown-pdf.mermaidServer` to the pinned URL |
| Still a code block, setting looks right | The setting is in user settings | Move it to `.vscode/settings.json` |
| "Syntax error in graph" only in the PDF | A label character the old renderer rejects | Fix the label (no `~`, parentheses, arrows, angle brackets) |
| Blank space where the diagram should be | Syntax error | Validate at [mermaid.live](https://mermaid.live) |
| No PDF at all | Chromium not found or download blocked | Set `markdown-pdf.executablePath` |

## A good default configuration

```json
{
  "markdown-pdf.mermaidServer": "https://unpkg.com/mermaid@9.4.3/dist/mermaid.min.js",
  "markdown-pdf.type": ["pdf"],
  "markdown-pdf.format": "A4",
  "markdown-pdf.printBackground": true,
  "markdown-pdf.displayHeaderFooter": true,
  "markdown-pdf.headerTemplate": "<div style=\"font-size: 9px; margin-left: 1cm;\"><span class='title'></span></div><div style=\"font-size: 9px; margin-left: auto; margin-right: 1cm;\">%%ISO-DATE%%</div>",
  "markdown-pdf.footerTemplate": "<div style=\"font-size: 9px; margin: 0 auto;\"><span class='pageNumber'></span> / <span class='totalPages'></span></div>",
  "markdown-pdf.margin.top": "1.5cm",
  "markdown-pdf.margin.bottom": "1cm",
  "markdown-pdf.margin.right": "1cm",
  "markdown-pdf.margin.left": "1cm",
  "markdown-pdf.styles": [".vscode/markdown-pdf.css"]
}
```

## Page breaks

Manual break in the Markdown source:

```html
<div class="page"/>
```

Keep diagrams, code and tables on one page with `.vscode/markdown-pdf.css`:

```css
.mermaid, pre, code, table { page-break-inside: avoid; }
h1, h2, h3, h4, h5, h6 { page-break-after: avoid; }
```

An element taller than a page still breaks: simplify or split it. Style paths are
relative to the workspace root; several files can be listed.

## Constraints

- Online CSS works for PNG and JPEG but is unreliable for PDF: keep styles local.
- Behind a proxy, set `http.proxy` in the editor settings and restart.
- For generated reports with charts and strict pagination, write HTML yourself instead
  (skill `docs-print-ready-pdf`).
