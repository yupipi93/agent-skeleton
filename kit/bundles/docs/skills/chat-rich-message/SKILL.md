---
name: chat-rich-message
description: "Produce copy-paste-ready chat messages that keep links, bold and lists in Teams, Google Chat, Slack or Gmail, via a local HTML page with Copy rich and Copy plain buttons. Use when the user wants a formatted message to paste into chat or email, or a pasted message lost its formatting."
---

# Rich chat messages: HTML, browser, clipboard

Chat apps do **not** render pasted Markdown source, but they **do** accept rich text
from the clipboard (the `text/html` flavour), which is exactly what a browser puts there
when you copy rendered content. So:

**build a local HTML page, open it in the browser, the user clicks Copy, then pastes.**

Links keep their display text, bold stays bold, lists stay lists.

## When to use

- A message with hyperlinks that have display text, bullet lists, bold, or
  emoji-structured sections.
- Many recipients at once: one personalised message per person.
- A plain or Markdown message already went out and lost its formatting.

Not for single-link or plain-prose messages (chat apps auto-link raw URLs), or Slack
when the user prefers typing native `*bold*` / `<url|text>`.

## Hard rules

1. **Local file only.** Never publish the page to a hosting service, a share link or a
   public artifact: these messages name colleagues, quote internal numbers and link
   internal systems. If a copy was published earlier, say so and offer to remove it.
2. **Open the page yourself** (`rich-message.py` does it). Do not end the turn telling
   the user to open a file.
3. **A copy button per message**, never "select all": a page with several messages
   cannot use it.
4. **No `<table>`, no images, no custom fonts or colours inside a message body.** Teams
   mangles pasted tables; the rest is stripped inconsistently.
5. **No credentials.** Refer to a password by which one it is, never by value.
   `rich-message.py` runs the text guard before opening (rule `outbound-text-safety`
   when the jira bundle is on).
6. **Plain punctuation.** Commas, colons, parentheses, ASCII hyphens. The template
   contains no em dash; keep it that way (rule `no-em-dash` in the style bundle).

## Workflow

### 1. Draft the content

- **The recipient's language**, not the language of your conversation with the user.
  Offer a second-language variant when the audience is mixed.
- **Short**: aim for 150 words or fewer per message. Detail belongs in the linked doc.
  Past 200 words, cut before delivering.
- **Real data, not adjectives.** When the agent can inspect the systems involved, put
  the actual number in the message (a coverage percentage, an error count, the one
  blocking dependency). One concrete fact plus one concrete next step.
- **Lead with what is true for them**: good news first, then the one action you want.
- **Self-degrading text**: the link's display text is itself the identifier
  (`api-service`, `PROJ-123`), so the message still informs if links are stripped.
- Shape: greeting, one line of context, a **bold lead sentence**, bullets with the
  specifics, grouped links, the closing ask. A couple of emoji, not more.
- **One idea per block** with a blank line between blocks. Bold the one concept and the
  concrete values; put a lone link last on its own line.

### 2. Write the draft, then build and open in one call

Write the draft as Markdown in a git-ignored, stable folder (the user reopens the page
while sending; not the session scratchpad), for example `local/messages/<topic>.md`,
then run:

```bash
kit/bundles/docs/scripts/rich-message.py local/messages/<topic>.md
```

That is the whole delivery, about half a second: it renders `<topic>.html` from
[assets/template.html](assets/template.html), runs the text guard and the em dash check
(exit 2 and nothing opened on a hit: fix the draft and re-run), and opens the page. Inside
Cursor or VS Code the page opens as a tab of the editor's own browser; elsewhere in the
system browser. Re-run after every edit. **Do not** copy the template by hand, take a
screenshot or syntax-check the page for a normal message: the script and its tests
cover that.

A plain Markdown file is one message. For several recipients or messages:

```markdown
# Release notes
=== Recipient A | recipient-a@example.com | Team A
ctx: module-x **26.7 %**, waiting on the PR
--- Message 1: announcement
attach: 📎 Attach the guide as PDF
Hi there,

**The lead fact.** One clause of nuance.

- Specific point with **the number**
- [PROJ-123](https://example.com/PROJ-123)
--- Message 2: follow-up
Second message, sent separately.
=== Luis | | Team B
Hi Luis, ...
```

`# title` (first line only) names the page; `=== name | email | group` starts a card;
`ctx:` is sender-only context, never copied; `--- label` starts another message in the
card; `attach:` adds the file reminder under it.

Body Markdown: paragraphs, line breaks, `-` bullets (indent to nest), `1.` lists,
`**bold**`, `*italic*`, `[text](url)`, bare URLs. Raw HTML is escaped, so the page only
holds paste-safe tags. A `## heading` becomes a bold line.

The page gives every message **Copy rich** (selects the rendered node and calls
`document.execCommand("copy")`, which puts `text/html` and `text/plain` on the
clipboard; the async Clipboard API is not reliable on `file://`), **Copy plain** (for
WhatsApp, Telegram or SMS: full URLs, `- ` bullets), the attachment reminder and the
sender context strip outside the copied node.

### 3. Editor browser (one-time setup)

The editor tab needs the small `editor-browser-open` extension (a URI handler,
`kit/bundles/docs/editor-extension/`). Install or update it with
`kit/bundles/docs/scripts/install-editor-browser.sh` (also run by
`bin/skeleton setup docs`). Without it, or with `BROWSER_OPEN_TARGET=system`, pages open
in the system browser; `BROWSER_OPEN_CMD` (for example `open -a "Google Chrome"`) still
wins over both.

### 4. By hand (rare)

For a layout the draft format cannot express, copy the template, fill `MSGS` (HTML
bodies, paste-safe tags only), run the text guard on it and open it with
`kit/bundles/docs/scripts/open-local.sh <page>.html`. Then check the render once with
`kit/bundles/docs/scripts/chrome.sh screenshot <page>.html <png> 1080,1400`.

### 5. Hand it over

Say the page is open and give its path, so the user can reopen it.

### 6. Tell the user how to paste

> Click **Copy rich**, then paste with a normal Cmd+V / Ctrl+V. Never "paste as plain
> text": that is what strips the links.

| App | On paste |
|---|---|
| Google Chat | Links and bold kept; bullets may become dashes (fine) |
| Microsoft Teams | Links, bold and bullet lists kept |
| Slack | Rich paste works; native markup is an alternative |
| Gmail, Outlook web | Full fidelity |
| WhatsApp, Telegram | Formatting stripped: use **Copy plain** |

## Checklist

- [ ] Recipient language right; second-language variant offered if mixed
- [ ] Each message about 150 words or fewer; detail pushed to the linked doc
- [ ] Personalised with real, verified numbers
- [ ] Link display text doubles as the identifier
- [ ] No credentials, tokens or internal-only endpoints (the script's guard passed)
- [ ] Draft saved outside the scratchpad; page built and **opened** by `rich-message.py`
- [ ] Not published anywhere
