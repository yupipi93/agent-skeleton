#!/usr/bin/env python3
"""Resolve which gcloud account to use for a project id, from a local routing map.

The map lives in ~/.config/agent-skeleton/gcp.env (KEY=VALUE, mode 0600) or in the
environment variable of the same name:

  GCP_ACCOUNT_MAP="acme-*=work@example.com client-*=you@example.org *=you@example.com"

Entries are `<glob>=<account>`, separated by spaces, commas or newlines (\\n in a
quoted value). The FIRST matching glob wins, so list specific patterns before broad
ones. Usage:

  kit/bundles/gcp/scripts/gcp-account.py my-project-dev     # prints the account
  kit/bundles/gcp/scripts/gcp-account.py --list             # prints the map
  gcloud run services list --project=my-project-dev \\
    --account="$(kit/bundles/gcp/scripts/gcp-account.py my-project-dev)"

Exit codes: 0 resolved, 1 no pattern matches (or no map), 2 bad usage.
It never runs gcloud and never changes the active account. Python 3.8+, stdlib only.
"""
import argparse
import fnmatch
import os
import re
import sys
from pathlib import Path

DEFAULT_FILE = "~/.config/agent-skeleton/gcp.env"
KEY = "GCP_ACCOUNT_MAP"

_LIB = Path(__file__).resolve().parents[2] / "core" / "scripts" / "lib"
sys.path.insert(0, str(_LIB))
try:
    import envfile  # noqa: E402
except ImportError:  # the core bundle is always present; this is a safety net
    envfile = None


def read_map(path):
    raw = None
    if envfile is not None:
        raw = envfile.get(path, KEY)
    else:
        raw = os.environ.get(KEY)
    if not raw:
        return []
    entries = []
    for item in re.split(r"[\s,]+|\\n", raw.strip()):
        if not item:
            continue
        if "=" not in item:
            sys.stderr.write("warning: ignoring malformed entry %r (expected glob=account)\n" % item)
            continue
        pattern, account = item.split("=", 1)
        if pattern and account:
            entries.append((pattern, account))
    return entries


def resolve(entries, project):
    for pattern, account in entries:
        if fnmatch.fnmatchcase(project, pattern):
            return account, pattern
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Which gcloud account owns this project id?")
    ap.add_argument("project", nargs="?", help="GCP project id, e.g. my-project-dev")
    ap.add_argument("--list", action="store_true", help="print the routing map")
    ap.add_argument("--file", default=os.environ.get("GCP_ACCOUNT_FILE", DEFAULT_FILE),
                    help="config file (default %s)" % DEFAULT_FILE)
    ap.add_argument("--explain", action="store_true", help="also print the matching pattern on stderr")
    args = ap.parse_args(argv)

    path = os.path.expanduser(args.file)
    if envfile is not None and os.path.exists(path):
        ok, mode = envfile.check_mode(path)
        if not ok:
            sys.stderr.write("warning: %s has mode %s; chmod 600 it\n" % (args.file, mode))
    entries = read_map(path)

    if args.list:
        if not entries:
            print("no %s configured (file %s or environment)" % (KEY, args.file))
            return 1
        for pattern, account in entries:
            print("%-30s %s" % (pattern, account))
        return 0
    if not args.project:
        ap.print_usage(sys.stderr)
        return 2
    if not entries:
        sys.stderr.write("error: no %s in %s or the environment; see skill gcp-identity-routing\n"
                         % (KEY, args.file))
        return 1
    account, pattern = resolve(entries, args.project)
    if not account:
        sys.stderr.write("error: no pattern in %s matches %r; ask which account owns it\n"
                         % (KEY, args.project))
        return 1
    if args.explain:
        sys.stderr.write("%s matched %s\n" % (args.project, pattern))
    print(account)
    return 0


if __name__ == "__main__":
    sys.exit(main())
