#!/usr/bin/env python3
"""Block a draft for people that is longer than its kind allows.

Readers stop reading long text. Every kind of text has a character budget; a draft over
it is cut before it is shown or sent:

  kit/bundles/style/scripts/text-budget.py --kind chat draft.md
  printf '%s' "$text" | kit/bundles/style/scripts/text-budget.py --kind comment
  kit/bundles/style/scripts/text-budget.py --list

Only what a person reads is counted: fenced code blocks, URLs (a Markdown link counts
its text only), Markdown markup (`**`, backticks, heading and list markers) and repeated
whitespace are left out. Commands and links cost nothing; prose does.

Budgets (characters), overridable per kind with TEXT_BUDGET_<KIND> in the environment or
in ~/.config/agent-skeleton/style.env, and for one run with --max:

  chat     200  Chat, Teams, Slack, WhatsApp message
  comment  250  ticket or PR comment
  notify   160  push notification
  commit   250  commit message, subject and body
  email    450  email body
  pr       500  pull request body
  ticket   500  ticket description
  post     600  social post, announcement
  reply    600  an agent's reply to its user
  voice    900  spoken summary (about one minute)

Exit codes: 0 within budget, 2 over budget (prints how much to cut), 64 usage error.
Read-only, Python 3.8+, stdlib only.
"""
import argparse
import os
import re
import sys
from pathlib import Path

DEFAULTS = {
    "chat": 200,
    "comment": 250,
    "notify": 160,
    "commit": 250,
    "email": 450,
    "pr": 500,
    "ticket": 500,
    "post": 600,
    "reply": 600,
    "voice": 900,
}

CONFIG = Path(os.path.expanduser("~/.config/agent-skeleton/style.env"))
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def config_value(key):
    """Environment first, then the style.env file; None when unset."""
    if os.environ.get(key, "").strip():
        return os.environ[key].strip()
    try:
        lines = CONFIG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        m = _LINE_RE.match(line)
        if m and m.group(1) == key:
            return m.group(2).strip().strip("'\"") or None
    return None


def budget_for(kind):
    raw = config_value("TEXT_BUDGET_" + kind.upper())
    if raw is None:
        return DEFAULTS[kind], "default"
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit("text-budget: TEXT_BUDGET_%s is not a number" % kind.upper())
    return value, "config"


FENCE_RE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.S | re.M)
MD_LINK_RE = re.compile(r"\[([^\]\n]*)\]\((?:[^)\s]+)\)")
URL_RE = re.compile(r"(?:https?|ftp)://\S+|\bwww\.\S+")
LINE_MARK_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s?|[-*+•]\s+|\d+[.)]\s+)", re.M)
EMPHASIS_RE = re.compile(r"\*\*|__|`")


def readable(text):
    """The part of the text a person actually reads."""
    text = FENCE_RE.sub(" ", text)
    text = MD_LINK_RE.sub(r"\1", text)
    text = URL_RE.sub(" ", text)
    text = LINE_MARK_RE.sub("", text)
    text = EMPHASIS_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Block a draft that is longer than its kind allows.")
    p.add_argument("path", nargs="?", help="draft file (default: stdin)")
    p.add_argument("--file", help="draft file (same as the positional path)")
    p.add_argument("--kind", choices=sorted(DEFAULTS), help="kind of text")
    p.add_argument("--max", type=int, help="budget for this run only")
    p.add_argument("--list", action="store_true", help="print the budgets in force")
    args = p.parse_args(argv)

    if args.list:
        for kind in DEFAULTS:
            value, source = budget_for(kind)
            print("%-8s %5d  %s" % (kind, value, source))
        return 0
    if not args.kind and args.max is None:
        p.print_usage(sys.stderr)
        print("text-budget: give --kind (or --max)", file=sys.stderr)
        return 64

    path = args.file or args.path
    try:
        text = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    except OSError as exc:
        print("text-budget: cannot read %s (%s)" % (path, exc.strerror), file=sys.stderr)
        return 64

    if args.max is not None:
        limit = args.max
    else:
        limit, _ = budget_for(args.kind)
    label = args.kind or "text"
    count = len(readable(text))

    if count <= limit:
        print("text-budget: ok, %s %d/%d chars" % (label, count, limit))
        return 0
    over = count - limit
    print("text-budget: over, %s %d/%d chars. Cut %d (%d%%): keep the ask and the facts, "
          "move detail to the ticket or doc and link it." % (
              label, count, limit, over, round(100 * over / count)))
    return 2


if __name__ == "__main__":
    sys.exit(main())
