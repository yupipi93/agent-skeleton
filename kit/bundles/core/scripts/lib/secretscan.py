#!/usr/bin/env python3
"""Python access to the shared secret patterns (lib/secret-patterns.txt).

    from secretscan import scan
    label = scan(text)          # None when clean, else the pattern label

CLI: secretscan.py [FILE]  (stdin when omitted). Exit 0 clean, 2 on a match.
The label is printed, never the matched text. Python 3.8+ compatible.
"""
import os
import re
import sys

PATTERNS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secret-patterns.txt")
_POSIX = {
    "[:space:]": r"\s", "[:alnum:]": "A-Za-z0-9", "[:alpha:]": "A-Za-z",
    "[:digit:]": "0-9", "[:upper:]": "A-Z", "[:lower:]": "a-z",
}
EM_DASH = "\u2014"


def _to_python(ere):
    for k, v in _POSIX.items():
        ere = ere.replace(k, v)
    return ere


def load_patterns(path=PATTERNS_FILE):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                out.append((parts[0], re.compile(_to_python(parts[1].strip()))))
    return out


def scan(text, em_dash=False, patterns=None):
    """Return the label of the first matching pattern, or None."""
    for label, rx in patterns if patterns is not None else load_patterns():
        if rx.search(text):
            return label
    if em_dash and EM_DASH in text:
        return "em-dash"
    return None


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--em-dash"]
    data = open(args[0], encoding="utf-8").read() if args else sys.stdin.read()
    hit = scan(data, em_dash="--em-dash" in sys.argv[1:])
    if hit:
        sys.stderr.write("secretscan: possible secret (%s)\n" % hit)
        sys.exit(2)
    sys.exit(0)
