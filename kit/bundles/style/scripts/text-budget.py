#!/usr/bin/env python3
"""Keep a draft for people as short as possible: a target to aim for, a hard maximum.

Readers stop reading long text. Every kind of text has a target (what a person would
write) and a maximum (never more). Write for the target; the maximum is a ceiling, not
a size to fill:

  kit/bundles/style/scripts/text-budget.py --kind chat draft.md
  printf '%s' "$text" | kit/bundles/style/scripts/text-budget.py --kind comment
  kit/bundles/style/scripts/text-budget.py --list

Only what a person reads is counted: fenced code blocks, URLs (a Markdown link counts
its text only), Markdown markup (`**`, backticks, heading and list markers) and repeated
whitespace are left out. Commands and links cost nothing; prose does.

Characters (target / maximum):

  chat      80 / 200  Chat, Teams, Slack, WhatsApp message
  notify    80 / 160  push notification
  commit   100 / 250  commit message, subject and body
  comment  120 / 250  ticket or PR comment
  email    250 / 450  email body
  pr       300 / 500  pull request body
  ticket   300 / 500  ticket description
  post     300 / 600  social post, announcement
  reply    300 / 600  an agent's reply to its user
  voice    500 / 900  spoken summary (30 to 60 seconds)

Override per kind with TEXT_TARGET_<KIND> and TEXT_BUDGET_<KIND> (the maximum) in the
environment or in ~/.config/agent-skeleton/style.env; --max N sets the maximum (and caps
the target) for one run.

Exit codes: 0 within target, 1 over target (shorten it if you can), 2 over the maximum
(cut it), 64 usage error. Read-only, Python 3.8+, stdlib only.
"""
import argparse
import os
import re
import sys
from pathlib import Path

DEFAULTS = {  # kind: (target, maximum)
    "chat": (80, 200),
    "notify": (80, 160),
    "commit": (100, 250),
    "comment": (120, 250),
    "email": (250, 450),
    "pr": (300, 500),
    "ticket": (300, 500),
    "post": (300, 600),
    "reply": (300, 600),
    "voice": (500, 900),
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


def _number(key, default):
    raw = config_value(key)
    if raw is None:
        return default, False
    try:
        return int(raw), True
    except ValueError:
        raise SystemExit("text-budget: %s is not a number" % key)


def limits_for(kind):
    """(target, maximum, source) for a kind; the target never exceeds the maximum."""
    target, maximum = DEFAULTS[kind]
    maximum, max_set = _number("TEXT_BUDGET_" + kind.upper(), maximum)
    target, target_set = _number("TEXT_TARGET_" + kind.upper(), target)
    source = "config" if (max_set or target_set) else "default"
    return min(target, maximum), maximum, source


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
        description="Keep a draft as short as possible: a target and a hard maximum.")
    p.add_argument("path", nargs="?", help="draft file (default: stdin)")
    p.add_argument("--file", help="draft file (same as the positional path)")
    p.add_argument("--kind", choices=sorted(DEFAULTS), help="kind of text")
    p.add_argument("--max", type=int, help="maximum for this run only")
    p.add_argument("--list", action="store_true", help="print the limits in force")
    args = p.parse_args(argv)

    if args.list:
        print("%-8s %6s %5s" % ("kind", "target", "max"))
        for kind in DEFAULTS:
            target, maximum, source = limits_for(kind)
            print("%-8s %6d %5d  %s" % (kind, target, maximum, source))
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

    if args.kind:
        target, maximum, _ = limits_for(args.kind)
    else:
        target = maximum = args.max
    if args.max is not None:
        maximum = args.max
        target = min(target, maximum)
    label = args.kind or "text"
    count = len(readable(text))

    if count <= target:
        print("text-budget: ok, %s %d chars (target %d, max %d)" % (label, count, target, maximum))
        return 0
    if count <= maximum:
        print("text-budget: long, %s %d chars. Target %d: cut %d if you can; a person "
              "would say it in fewer (max %d)." % (label, count, target, count - target, maximum))
        return 1
    over = count - maximum
    print("text-budget: over, %s %d/%d chars. Cut %d (%d%%): keep the ask and the facts, "
          "move detail to the ticket or doc and link it. Target %d." % (
              label, count, maximum, over, round(100 * over / count), target))
    return 2


if __name__ == "__main__":
    sys.exit(main())
