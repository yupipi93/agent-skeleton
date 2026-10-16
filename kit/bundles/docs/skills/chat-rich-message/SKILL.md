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
2. **Open the browser yourself** (step 4). Do not end the turn telling the user to
   open a file.
3. **A copy button per message**, never "select all": a page with several messages
   cannot use it.
4. **No `<table>`, no images, no custom fonts or colours inside a message body.** Teams
   mangles pasted tables; the rest is stripped inconsistently.
5. **No credentials.** Refer to a password by which one it is, never by value. Run the
   draft through `kit/bundles/core/scripts/text-guard.sh --file <page>.html` before
   opening it (rule `outbound-text-safety` when the jira bundle is on).
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

### 2. Build the page

Start from [assets/template.html](assets/template.html): a working scaffold with the
copy machinery in place. Fill the `MSGS` array; keep everything inline (style, script,
no external assets). Inside a message body use only paste-safe elements: `<p>`, `<b>`,
`<strong>`, `<i>`, `<ul>`, `<ol>`, `<li>`, `<a href>`, `<br>`, emoji.

Every message gets:

- **Copy rich**: selects the rendered node and calls `document.execCommand("copy")`,
  which puts both `text/html` and `text/plain` on the clipboard. Deliberately not
  `navigator.clipboard.write`: the async Clipboard API is not reliably available on
  `file://`.
- **Copy plain**: for WhatsApp, Telegram or SMS, which strip formatting; URLs are written
  out in full and bullets become `- `.
- **An attachment reminder** when a file must go with the message.
- **A "context for you" strip** with facts for the sender (status, numbers, what to
  watch), outside the copied node so it never lands in the message.

Several recipients: one card per person, grouped by team, each with their own links and
facts.

### 3. Save it somewhere stable

Not the session scratchpad: the user reopens the page while sending. Use a git-ignored
folder of the workspace, for example `local/messages/<topic>.html` (`local/` is
git-ignored), unless the user names another place.

### 4. Open it

```bash
kit/bundles/docs/scripts/open-local.sh local/messages/<topic>.html
```

It uses `$BROWSER_OPEN_CMD` when set (for example `open -a "Google Chrome"`), else
`open` on macOS, else `xdg-open` (Linux) or `wslview` (WSL), and returns immediately.
Re-open it after every edit so the user sees the current version.

### 5. Verify before delivering

```bash
kit/bundles/docs/scripts/chrome.sh screenshot local/messages/<topic>.html /tmp/messages.png 1080,1400
```

Read the PNG. Check: the expected number of cards, links present, no raw markup leaking
into a body, no `<table>` inside a message. When `node` is available, also check the
script parses (copy the `<script>` body to a file and run `node --check` on it).

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
- [ ] Text guard passed: no credentials, tokens or internal-only endpoints
- [ ] Only paste-safe elements in bodies; no `<table>`
- [ ] Copy rich and Copy plain on every message; sender context outside the copied node
- [ ] Saved outside the scratchpad; render checked; **opened by the agent**
- [ ] Not published anywhere
