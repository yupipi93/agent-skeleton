#!/usr/bin/env python3
"""Turn a short Markdown draft into the chat-rich-message page, check it and open it.

One call replaces "copy the template, fill MSGS, scan, screenshot, open":

  kit/bundles/docs/scripts/rich-message.py local/messages/<topic>.md
  kit/bundles/docs/scripts/rich-message.py --no-open draft.md -o page.html

The page is written next to the draft (<topic>.html) from
kit/bundles/docs/skills/chat-rich-message/assets/template.html and opened with
open-local.sh (the editor's built-in browser when the agent runs inside Cursor or
VS Code, else the system browser).

Draft format. A plain Markdown file is one message. For several, split it:

  # Page title                     optional, first line only
  === Name | email | Group         starts a card (email and group optional)
  ctx: sender-only context         never copied; may repeat
  --- Label                        starts another message in the same card
  attach: 📎 Attach the guide      reminder under the message
  body in Markdown

Body Markdown: paragraphs, line breaks, "- " / "* " bullets (indent 2+ spaces to
nest), "1. " lists, **bold**, *italic* / _italic_, [text](url), bare URLs, `code`
(kept as plain text), a "## heading" line becomes a bold paragraph. Raw HTML is
escaped: the page only ever holds paste-safe tags.

Checks (exit 2 on failure, nothing opened): text-guard secret scan, no em dash,
at least one non-empty message.

Environment:
  RICH_MESSAGE_TEMPLATE  template path (default: the skill's assets/template.html)
  BROWSER_OPEN_CMD, BROWSER_OPEN_TARGET  passed through to open-local.sh
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = Path(os.environ.get(
    "RICH_MESSAGE_TEMPLATE", HERE.parent / "skills/chat-rich-message/assets/template.html"))
TEXT_GUARD = HERE.parent.parent / "core/scripts/text-guard.sh"
OPEN_LOCAL = HERE / "open-local.sh"
MSGS_RE = re.compile(r"(?<=const MSGS = )/\*MSGS\*/.*?/\*END\*/", re.S)
TITLE_RE = re.compile(r"(?<=const TITLE = )/\*TITLE\*/.*?/\*END\*/", re.S)

URL_RE = r"https?://[^\s<>()]+[^\s<>().,;:!?'\"]"
INLINE_RE = re.compile(
    r"\[(?P<lt>[^\]]+)\]\((?P<lu>[^)\s]+)\)"
    r"|\*\*(?P<b>.+?)\*\*"
    r"|(?<![\w*])\*(?P<i>[^*\s][^*]*?)\*(?![\w*])"
    r"|(?<!\w)_(?P<u>[^_\s][^_]*?)_(?!\w)"
    r"|`(?P<c>[^`]+)`"
    rf"|(?P<url>{URL_RE})")
LIST_RE = re.compile(r"^(?P<ind>\s*)(?P<mark>[-*+]|\d+[.)])\s+(?P<text>.*)$")


def inline(text: str) -> str:
    """Escape text and render the inline Markdown subset."""
    out, pos = [], 0
    for m in INLINE_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        g = m.groupdict()
        if g["lt"] is not None:
            out.append(f'<a href="{html.escape(g["lu"])}">{inline(g["lt"])}</a>')
        elif g["b"] is not None:
            out.append(f"<b>{inline(g['b'])}</b>")
        elif g["i"] is not None or g["u"] is not None:
            out.append(f"<i>{inline(g['i'] or g['u'])}</i>")
        elif g["c"] is not None:
            out.append(html.escape(g["c"], quote=False))
        else:
            out.append(f'<a href="{html.escape(g["url"])}">{html.escape(g["url"], quote=False)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def render_list(items: list[tuple[int, bool, str]]) -> str:
    """items: (indent, ordered, text) in order; nests by indent."""
    html_out: list[str] = []
    stack: list[tuple[int, str]] = []  # (indent, tag)
    for ind, ordered, text in items:
        tag = "ol" if ordered else "ul"
        if not stack or ind > stack[-1][0]:
            html_out.append(f"<{tag}>")
            stack.append((ind, tag))
        else:
            while len(stack) > 1 and ind < stack[-1][0]:
                html_out.append(f"</li></{stack.pop()[1]}>")
            if len(stack) == 1 and stack[0][1] != tag:  # "1." after "-": a new list
                html_out.append(f"</li></{stack.pop()[1]}><{tag}>")
                stack.append((ind, tag))
            else:
                html_out.append("</li>")
        html_out.append(f"<li>{inline(text)}")
    while stack:
        html_out.append(f"</li></{stack.pop()[1]}>")
    return "".join(html_out)


def md_to_html(md: str) -> str:
    blocks: list[str] = []
    para: list[str] = []
    items: list[tuple[int, bool, str]] = []

    def flush():
        if para:
            blocks.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>")
            para.clear()
        if items:
            blocks.append(render_list(items))
            items.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        m = LIST_RE.match(line)
        if not line.strip():
            flush()
        elif m:
            if para:
                flush()
            ind = len(m["ind"].expandtabs(4))
            items.append((ind, m["mark"][0].isdigit(), m["text"]))
        elif items and raw.startswith("  "):
            ind, ordered, text = items[-1]
            items[-1] = (ind, ordered, text + " " + line.strip())
        elif line.lstrip().startswith("#"):
            flush()
            blocks.append(f"<p><b>{inline(line.lstrip('#').strip())}</b></p>")
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(blocks)


def parse(text: str) -> tuple[str | None, list[dict]]:
    lines = text.splitlines()
    title = None
    if lines and lines[0].startswith("# "):
        title = lines.pop(0)[2:].strip()
    cards: list[dict] = []
    card = msg = None

    def new_card(name="", email="", group=""):
        nonlocal card, msg
        card = {"group": group, "name": name, "email": email, "ctx": "", "msgs": []}
        cards.append(card)
        msg = None

    def new_msg(label=""):
        nonlocal msg
        msg = {"label": label, "attach": "", "md": []}
        card["msgs"].append(msg)

    for line in lines:
        if line.startswith("=== "):
            parts = [p.strip() for p in line[4:].split("|")] + ["", ""]
            new_card(parts[0], parts[1], parts[2])
            continue
        if card is None:
            if not line.strip():
                continue
            new_card()
        if line.startswith("--- ") or line.strip() == "---":
            new_msg(line[4:].strip())
        elif line.startswith("ctx:") and (msg is None or not "".join(msg["md"]).strip()):
            card["ctx"] += (" · " if card["ctx"] else "") + inline(line[4:].strip())
        elif line.startswith("attach:") and msg is not None:
            msg["attach"] = html.escape(line[7:].strip(), quote=False)
        else:
            if msg is None:
                new_msg()
            msg["md"].append(line)

    for c in cards:
        for m in c["msgs"]:
            m["body"] = md_to_html("\n".join(m.pop("md")))
        c["msgs"] = [m for m in c["msgs"] if m["body"]]
    return title, [c for c in cards if c["msgs"]]


def build(src: Path, out: Path) -> int:
    text = src.read_text(encoding="utf-8")
    if "\u2014" in text:
        bad = [i for i, l in enumerate(text.splitlines(), 1) if "\u2014" in l]
        print(f"rich-message: em dash on line(s) {bad} of {src}; use a comma, colon or parentheses",
              file=sys.stderr)
        return 2
    if TEXT_GUARD.exists():
        rc = subprocess.run([str(TEXT_GUARD), "--file", str(src)]).returncode
        if rc != 0:
            print(f"rich-message: text guard blocked {src}; nothing written", file=sys.stderr)
            return 2
    title, cards = parse(text)
    if not cards:
        print(f"rich-message: no message body in {src}", file=sys.stderr)
        return 2
    page = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(cards, ensure_ascii=False, indent=1).replace("</", "<\\/")
    page = MSGS_RE.sub(lambda _: data, page, count=1)
    page = TITLE_RE.sub(lambda _: json.dumps(title or "Messages to send", ensure_ascii=False), page, count=1)
    out.write_text(page, encoding="utf-8")
    n = sum(len(c["msgs"]) for c in cards)
    print(f"✅ {out} ({len(cards)} card(s), {n} message(s))")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("draft", type=Path, help="Markdown draft")
    ap.add_argument("-o", "--out", type=Path, help="page path (default: draft with .html)")
    ap.add_argument("--no-open", action="store_true", help="write and check only")
    a = ap.parse_args()
    if not a.draft.is_file():
        print(f"rich-message: no such file: {a.draft}", file=sys.stderr)
        return 2
    out = a.out or a.draft.with_suffix(".html")
    rc = build(a.draft, out)
    if rc == 0 and not a.no_open:
        rc = subprocess.run([str(OPEN_LOCAL), str(out)]).returncode
    return rc


if __name__ == "__main__":
    sys.exit(main())
