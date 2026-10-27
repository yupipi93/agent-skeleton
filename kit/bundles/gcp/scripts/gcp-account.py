#!/usr/bin/env python3
"""Resolve which gcloud account to use for a project id, from a local routing map.

The map lives in ~/.config/agent-skeleton/gcp.env (KEY=VALUE, mode 0600) or in the
environment variable of the same name:

  GCP_ACCOUNT_MAP="acme-*=work@example.com client-*=you@example.org *=you@example.com"

Entries are `<glob>=<account>`, separated by spaces, commas or newlines (\\n in a
quoted value). The FIRST matching glob wins, so list specific patterns before broad
ones.

When no glob matches, the project is looked up in the learned file
(~/.config/agent-skeleton/gcp-account-learned.txt, `project=account` lines). Still
unknown: each account of the map is asked, read-only, whether it can see the project
(`gcloud projects describe`), and the one that can is learned, so a new project never
needs a manual map edit. When several accounts see it, the one whose own organization
holds the project wins (`projects get-ancestors`, `organizations list`). `--sync`
learns, or corrects, every project the accounts can list.
Set GCP_ACCOUNT_DISCOVER=0 (or pass --no-discover) to keep it to the map alone.

Usage:

  kit/bundles/gcp/scripts/gcp-account.py my-project-dev     # prints the account
  kit/bundles/gcp/scripts/gcp-account.py --list             # prints the map and learned ids
  kit/bundles/gcp/scripts/gcp-account.py --sync             # learn every visible project
  gcloud run services list --project=my-project-dev \\
    --account="$(kit/bundles/gcp/scripts/gcp-account.py my-project-dev)"

Exit codes: 0 resolved, 1 no account found (or no map), 2 bad usage.
gcloud runs only read-only (describe, list) and never changes the active account.
Python 3.8+, stdlib only.
"""
import argparse
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_FILE = "~/.config/agent-skeleton/gcp.env"
DEFAULT_LEARNED = "~/.config/agent-skeleton/gcp-account-learned.txt"
KEY = "GCP_ACCOUNT_MAP"
GCLOUD_TIMEOUT = 60

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


def accounts_of(entries):
    seen = []
    for _, account in entries:
        if account not in seen:
            seen.append(account)
    return seen


def read_learned(path):
    learned = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return learned
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            project, account = line.split("=", 1)
            learned[project.strip()] = account.strip()
    return learned


def write_learned(path, learned):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "# Learned by kit/bundles/gcp/scripts/gcp-account.py: project=account, safe to delete\n"
    body += "".join("%s=%s\n" % kv for kv in sorted(learned.items()))
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(p)


def gcloud(*args):
    try:
        proc = subprocess.run(["gcloud", *args], capture_output=True, text=True, timeout=GCLOUD_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


class Picker:
    """Chooses among the accounts that can see a project: the one whose own organization
    holds it (a project shared with a guest account still belongs to its home org)."""

    def __init__(self, accounts):
        self.accounts = accounts
        self._orgs = None

    def home_orgs(self):
        if self._orgs is None:
            self._orgs = {}
            for account in self.accounts:
                out = gcloud("organizations", "list", "--account=" + account, "--format=value(name)")
                self._orgs[account] = {n.rsplit("/", 1)[-1] for n in (out or "").split()}
        return self._orgs

    def pick(self, project, found):
        if len(found) == 1:
            return found[0]
        out = gcloud("projects", "get-ancestors", project, "--account=" + found[0],
                     "--format=value(id,type)") or ""
        org = next((line.split()[0] for line in out.splitlines()
                    if line.split()[-1:] == ["organization"]), None)
        for account in found:
            if org and org in self.home_orgs().get(account, ()):
                return account
        sys.stderr.write("warning: %s is visible to %s and its organization is none of theirs; "
                         "using %s (add a glob to %s to choose)\n"
                         % (project, ", ".join(found), found[0], KEY))
        return found[0]


def discover(entries, project):
    """The account that can describe the project; its home org breaks a tie."""
    accounts = accounts_of(entries)
    found = []
    for account in accounts:
        out = gcloud("projects", "describe", project, "--account=" + account,
                     "--format=value(projectId)")
        if out and out.strip() == project:
            found.append(account)
    return Picker(accounts).pick(project, found) if found else None


def sync(entries, learned):
    """Learn (or correct) every project the accounts can list that no glob routes."""
    accounts = accounts_of(entries)
    visible = {}
    for account in accounts:
        out = gcloud("projects", "list", "--account=" + account, "--format=value(projectId)")
        if out is None:
            sys.stderr.write("warning: could not list projects as %s (expired login?)\n" % account)
            continue
        for project in out.split():
            if not resolve(entries, project)[0]:
                visible.setdefault(project, []).append(account)
    picker = Picker(accounts)
    changed = 0
    for project, found in sorted(visible.items()):
        account = picker.pick(project, found)
        if learned.get(project) != account:
            learned[project] = account
            changed += 1
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Which gcloud account owns this project id?")
    ap.add_argument("project", nargs="?", help="GCP project id, e.g. my-project-dev")
    ap.add_argument("--list", action="store_true", help="print the routing map and learned ids")
    ap.add_argument("--sync", action="store_true", help="learn every project each account can list")
    ap.add_argument("--file", default=os.environ.get("GCP_ACCOUNT_FILE", DEFAULT_FILE),
                    help="config file (default %s)" % DEFAULT_FILE)
    ap.add_argument("--learned", default=os.environ.get("GCP_ACCOUNT_LEARNED", DEFAULT_LEARNED),
                    help="learned ids file (default %s)" % DEFAULT_LEARNED)
    ap.add_argument("--no-discover", action="store_true",
                    help="never ask gcloud; map and learned file only")
    ap.add_argument("--explain", action="store_true", help="also print the matching pattern on stderr")
    args = ap.parse_args(argv)
    discover_ok = not args.no_discover and os.environ.get("GCP_ACCOUNT_DISCOVER", "1") != "0"

    path = os.path.expanduser(args.file)
    learned_path = os.path.expanduser(args.learned)
    if envfile is not None and os.path.exists(path):
        ok, mode = envfile.check_mode(path)
        if not ok:
            sys.stderr.write("warning: %s has mode %s; chmod 600 it\n" % (args.file, mode))
    entries = read_map(path)
    learned = read_learned(learned_path)

    if args.list:
        if not entries:
            print("no %s configured (file %s or environment)" % (KEY, args.file))
            return 1
        for pattern, account in entries:
            print("%-30s %s" % (pattern, account))
        for project, account in sorted(learned.items()):
            print("%-30s %s (learned)" % (project, account))
        return 0
    if not entries:
        sys.stderr.write("error: no %s in %s or the environment; see skill gcp-identity-routing\n"
                         % (KEY, args.file))
        return 1
    if args.sync:
        changed = sync(entries, learned)
        write_learned(learned_path, learned)
        print("learned or corrected %d project(s); %d in %s" % (changed, len(learned), args.learned))
        return 0
    if not args.project:
        ap.print_usage(sys.stderr)
        return 2

    account, pattern = resolve(entries, args.project)
    if not account and args.project in learned:
        account, pattern = learned[args.project], "learned"
    if not account and discover_ok:
        account = discover(entries, args.project)
        if account:
            pattern = "discovered"
            learned[args.project] = account
            write_learned(learned_path, learned)
    if not account:
        sys.stderr.write("error: no account in %s can see %r (map, learned file%s); ask which "
                         "account owns it\n" % (KEY, args.project, ", gcloud" if discover_ok else ""))
        return 1
    if args.explain:
        sys.stderr.write("%s matched %s\n" % (args.project, pattern))
    print(account)
    return 0


if __name__ == "__main__":
    sys.exit(main())
