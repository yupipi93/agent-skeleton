#!/usr/bin/env python3
"""Markdown <-> ADF (Atlassian Document Format) for the jira bundle.

    from adf import md_to_adf, adf_to_markdown
    doc = md_to_adf(text, site="your-org.atlassian.net")
    text = adf_to_markdown(doc)

md_to_adf supports the subset that makes a ticket readable:
  - headings        # .. #####
  - GFM tables      | a | b |  followed by a |---|---| separator (first row = header)
  - bullet lists    - item          numbered lists   1. item
  - fenced code     ```lang ... ```
  - panels          > text  (first line "> [!warning]" picks info|note|success|warning|error)
  - inline          **bold**, `code`, [text](https://...), [[PROJ-123]] issue cards,
                    @[Display Name](<accountId>) mentions
  - paragraphs      blank-line separated; single newlines become hard breaks
  - emojis          plain unicode, passed through

adf_to_markdown is deliberately lossy: it exists to read a ticket in a terminal, and
unknown nodes recurse so no text is silently dropped.

CLI: adf.py to-adf [FILE] (stdin when omitted) [--site HOST]   prints ADF JSON
     adf.py to-md  [FILE]                                       prints Markdown

Python 3.8+ compatible, stdlib only.
"""
import json
import re
import sys

INLINE_RE = re.compile(
    r"\[\[(?P<card>[A-Z][A-Z0-9]+-\d+|https?://[^\]\s]+)\]\]"
    r"|@\[(?P<mname>[^\]]+)\]\((?P<mid>[0-9a-f]{6,}:[0-9a-f-]{36}|[0-9a-f]{24})\)"
    r"|\[(?P<ltext>[^\]]+)\]\((?P<lurl>https?://[^)\s]+)\)"
    r"|`(?P<code>[^`]+)`"
    r"|\*\*(?P<bold>.+?)\*\*"
)
_BULLET = re.compile(r"^\s*[-*]\s+")
_NUMBER = re.compile(r"^\s*\d+\.\s+")
_HEADING = re.compile(r"^(#{1,5})\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
_FENCE = re.compile(r"^\s*```\s*([A-Za-z0-9_+-]*)\s*$")


def inline(text, site=None):
    """Inline Markdown to a list of ADF text/card/mention nodes."""
    nodes = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            nodes.append({"type": "text", "text": text[pos:m.start()]})
        if m.group("card"):
            card = m.group("card")
            if card.startswith("http"):
                url = card
            elif site:
                url = "https://%s/browse/%s" % (site, card)
            else:
                url = None
            if url:
                nodes.append({"type": "inlineCard", "attrs": {"url": url}})
            else:
                nodes.append({"type": "text", "text": card})
        elif m.group("mid"):
            nodes.append({"type": "mention",
                          "attrs": {"id": m.group("mid"), "text": "@" + m.group("mname")}})
        elif m.group("ltext"):
            nodes.append({"type": "text", "text": m.group("ltext"),
                          "marks": [{"type": "link", "attrs": {"href": m.group("lurl")}}]})
        elif m.group("code"):
            nodes.append({"type": "text", "text": m.group("code"), "marks": [{"type": "code"}]})
        else:
            nodes.append({"type": "text", "text": m.group("bold"), "marks": [{"type": "strong"}]})
        pos = m.end()
    if pos < len(text):
        nodes.append({"type": "text", "text": text[pos:]})
    return nodes or [{"type": "text", "text": " "}]


def _paragraph(lines, site):
    content = []
    for i, line in enumerate(lines):
        if i > 0:
            content.append({"type": "hardBreak"})
        content.extend(inline(line, site))
    return {"type": "paragraph", "content": content}


def _split_row(line):
    return line.strip().strip("|").split("|")


def _table_row(cells, header, site):
    kind = "tableHeader" if header else "tableCell"
    return {"type": "tableRow",
            "content": [{"type": kind, "attrs": {}, "content": [_paragraph([c.strip()], site)]}
                        for c in cells]}


def _starts_block(line):
    s = line.lstrip()
    return (not line.strip() or s.startswith(("|", "#", ">")) or _BULLET.match(line)
            or _NUMBER.match(line) or _FENCE.match(line))


def md_to_adf(md, site=None):
    """Convert the supported Markdown subset to an ADF document (dict)."""
    doc = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = _FENCE.match(line)
        if fence:
            body = []
            i += 1
            while i < len(lines) and not _FENCE.match(lines[i]):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence (or end of text)
            node = {"type": "codeBlock", "content": [{"type": "text", "text": "\n".join(body) or " "}]}
            if fence.group(1):
                node["attrs"] = {"language": fence.group(1)}
            doc.append(node)
            continue
        m = _HEADING.match(line)
        if m:
            doc.append({"type": "heading", "attrs": {"level": len(m.group(1))},
                        "content": inline(m.group(2).strip(), site)})
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and \
                _TABLE_SEP.match(lines[i + 1]) and "-" in lines[i + 1]:
            rows = [_table_row(_split_row(line), True, site)]
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_table_row(_split_row(lines[i]), False, site))
                i += 1
            doc.append({"type": "table",
                        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
                        "content": rows})
            continue
        for rx, kind in ((_BULLET, "bulletList"), (_NUMBER, "orderedList")):
            if rx.match(line):
                items = []
                while i < len(lines) and rx.match(lines[i]):
                    items.append({"type": "listItem",
                                  "content": [_paragraph([rx.sub("", lines[i], count=1)], site)]})
                    i += 1
                node = {"type": kind, "content": items}
                if kind == "orderedList":
                    node["attrs"] = {"order": 1}
                doc.append(node)
                break
        else:
            if line.lstrip().startswith(">"):
                quoted = []
                while i < len(lines) and lines[i].lstrip().startswith(">"):
                    quoted.append(re.sub(r"^\s*>\s?", "", lines[i]))
                    i += 1
                kind = "info"
                m = re.match(r"^\[!(info|note|success|warning|error)\]\s*$", quoted[0], re.I)
                if m:
                    kind = m.group(1).lower()
                    quoted = quoted[1:]
                inner = md_to_adf("\n".join(quoted), site)["content"] or [_paragraph([" "], site)]
                doc.append({"type": "panel", "attrs": {"panelType": kind}, "content": inner})
                continue
            block = [line]
            i += 1
            while i < len(lines) and not _starts_block(lines[i]):
                block.append(lines[i])
                i += 1
            doc.append(_paragraph(block, site))
    return {"type": "doc", "version": 1, "content": doc}


def adf_to_markdown(node, depth=0):
    """Flatten ADF to readable Markdown (lossy)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    kind = node.get("type")
    content = node.get("content") or []
    attrs = node.get("attrs") or {}

    if kind == "text":
        text = node.get("text", "")
        marks = node.get("marks") or []
        names = {m.get("type") for m in marks}
        if "code" in names:
            text = "`%s`" % text
        if "strong" in names:
            text = "**%s**" % text
        if "em" in names:
            text = "_%s_" % text
        for mark in marks:
            if mark.get("type") == "link":
                text = "[%s](%s)" % (text, (mark.get("attrs") or {}).get("href", ""))
        return text
    if kind == "hardBreak":
        return "\n"
    if kind == "emoji":
        return attrs.get("text", "")
    if kind == "mention":
        return "@" + str(attrs.get("text", "")).lstrip("@")
    if kind in ("media", "mediaInline"):
        return "\n[embedded file, see the attachments]\n"
    if kind in ("inlineCard", "blockCard", "embedCard"):
        url = attrs.get("url", "")
        return url.rsplit("/browse/", 1)[-1] if "/browse/" in url else url

    if kind in ("bulletList", "orderedList"):
        out = []
        for n, item in enumerate(content, 1):
            prefix = "%d." % n if kind == "orderedList" else "-"
            body = "".join(adf_to_markdown(c, depth + 1) for c in item.get("content") or []).strip()
            out.append("%s%s %s\n" % ("  " * depth, prefix, body))
        return "\n" + "".join(out)

    inner = "".join(adf_to_markdown(c, depth) for c in content)
    if kind == "heading":
        return "\n%s %s\n" % ("#" * int(attrs.get("level", 1)), inner.strip())
    if kind == "paragraph":
        return "\n%s\n" % inner.strip()
    if kind == "codeBlock":
        return "\n```%s\n%s\n```\n" % (attrs.get("language", ""), inner)
    if kind == "blockquote":
        return "\n> %s\n" % inner.strip().replace("\n", "\n> ")
    if kind == "panel":
        return "\n> [%s] %s\n" % (str(attrs.get("panelType", "info")).upper(),
                                  inner.strip().replace("\n", "\n> "))
    if kind == "rule":
        return "\n---\n"
    if kind == "tableRow":
        cells = [adf_to_markdown(c, depth).strip().replace("\n", " ") for c in content]
        return "| " + " | ".join(cells) + " |\n"
    if kind == "table":
        rows = [adf_to_markdown(c, depth) for c in content]
        if rows:
            width = rows[0].count("|") - 1
            rows.insert(1, "|" + "|".join(["---"] * max(width, 1)) + "|\n")
        return "\n" + "".join(rows)
    return inner


def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(__doc__.split("CLI:", 1)[1].strip() + "\n")
        return 0 if argv else 64
    cmd, rest = argv[0], argv[1:]
    site = None
    if "--site" in rest:
        idx = rest.index("--site")
        site = rest[idx + 1] if idx + 1 < len(rest) else None
        rest = rest[:idx] + rest[idx + 2:]
    data = open(rest[0], encoding="utf-8").read() if rest else sys.stdin.read()
    if cmd == "to-adf":
        print(json.dumps(md_to_adf(data, site), ensure_ascii=False, indent=2))
        return 0
    if cmd == "to-md":
        print(adf_to_markdown(json.loads(data)).strip())
        return 0
    sys.stderr.write("adf.py: unknown command %r (to-adf | to-md)\n" % cmd)
    return 64


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
