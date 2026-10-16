#!/usr/bin/env python3
"""Read and write KEY=VALUE config files without `source`-ing them.

Config files live under ~/.config/agent-skeleton/ (mode 0600, directory 0700).
Usable as a module (`import envfile`) or as a CLI:

  envfile.py get FILE KEY [--default VALUE] [--no-env]
  envfile.py set FILE KEY [--value VALUE]   # without --value, reads the value from stdin
  envfile.py unset FILE KEY
  envfile.py keys FILE                      # key names only, never values
  envfile.py check-mode FILE                # exit 0 ok, 1 too open, 2 missing

`get` returns the environment variable KEY when it is set (scripts accept env
overrides for every key), unless --no-env is given. Secrets never need to be
passed on the command line: pipe them into `set` on stdin.

Kept compatible with Python 3.8+ because macOS ships an old python3.
"""
import argparse
import os
import re
import sys
import tempfile

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def _unquote(raw):
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == '"':
        out, i, body = [], 0, v[1:-1]
        while i < len(body):
            ch = body[i]
            if ch == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
                i += 2
                continue
            out.append(ch)
            i += 1
        return "".join(out)
    if " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return v


def _quote(value):
    if value == "" or re.search(r"[\s#'\"\\$`]", value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return value


def load(path):
    """Return a dict of every KEY=VALUE in the file ({} when missing)."""
    data = {}
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            for line in f:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                m = _LINE_RE.match(line.rstrip("\n"))
                if m:
                    data[m.group(1)] = _unquote(m.group(2))
    except FileNotFoundError:
        pass
    return data


def get(path, key, default=None, use_env=True):
    if use_env and os.environ.get(key):
        return os.environ[key]
    return load(path).get(key, default)


def check_mode(path):
    """Return (ok, mode_string). ok is False when group or others have any access."""
    st = os.stat(os.path.expanduser(path))
    mode = st.st_mode & 0o777
    return (mode & 0o077) == 0, oct(mode)


def _write_secure(path, text):
    path = os.path.expanduser(path)
    directory = os.path.dirname(path) or "."
    if not os.path.isdir(directory):
        os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".envfile-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_value(path, key, value):
    """Set KEY, keeping comments, order and other keys. Creates the file 0600."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        raise ValueError("invalid key: %r" % key)
    p = os.path.expanduser(path)
    lines = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines()
    new = "%s=%s" % (key, _quote(value))
    for i, line in enumerate(lines):
        m = _LINE_RE.match(line)
        if m and m.group(1) == key:
            lines[i] = new
            break
    else:
        lines.append(new)
    _write_secure(p, "\n".join(lines) + "\n")


def unset(path, key):
    p = os.path.expanduser(path)
    if not os.path.exists(p):
        return False
    with open(p, encoding="utf-8") as f:
        lines = f.read().splitlines()
    kept = [ln for ln in lines if not ((_LINE_RE.match(ln) or [None, None])[1] == key)]
    if len(kept) == len(lines):
        return False
    _write_secure(p, "\n".join(kept) + ("\n" if kept else ""))
    return True


def _main(argv):
    ap = argparse.ArgumentParser(prog="envfile.py", description="KEY=VALUE config files, safely.")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("get")
    g.add_argument("file")
    g.add_argument("key")
    g.add_argument("--default")
    g.add_argument("--no-env", action="store_true")
    s = sub.add_parser("set")
    s.add_argument("file")
    s.add_argument("key")
    s.add_argument("--value", help="non-secret values only; secrets go on stdin")
    u = sub.add_parser("unset")
    u.add_argument("file")
    u.add_argument("key")
    k = sub.add_parser("keys")
    k.add_argument("file")
    c = sub.add_parser("check-mode")
    c.add_argument("file")
    args = ap.parse_args(argv)

    if args.cmd == "get":
        value = get(args.file, args.key, args.default, use_env=not args.no_env)
        if value is None:
            return 1
        sys.stdout.write(value + "\n")
        return 0
    if args.cmd == "set":
        value = args.value
        if value is None:
            value = sys.stdin.read()
            if value.endswith("\n"):
                value = value[:-1]
        set_value(args.file, args.key, value)
        return 0
    if args.cmd == "unset":
        return 0 if unset(args.file, args.key) else 1
    if args.cmd == "keys":
        for key in load(args.file):
            print(key)
        return 0
    if args.cmd == "check-mode":
        p = os.path.expanduser(args.file)
        if not os.path.exists(p):
            sys.stderr.write("%s: missing\n" % args.file)
            return 2
        ok, mode = check_mode(p)
        if not ok:
            sys.stderr.write("%s: mode %s is too open; run chmod 600 %s\n" % (args.file, mode, args.file))
            return 1
        return 0
    ap.print_help()
    return 64


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
