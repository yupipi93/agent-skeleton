"""Command line entry point.

Exit codes: 0 ok (or plan printed), 1 a step failed, 2 bad usage, 3 not signed
in, 5 Secret Manager failed after the token was created (it is kept in the
stash), 6 a token with that name already exists, 7 the browser is signed in as
another account than the expected one.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import account, config, redact, sm, stash
from .bitbucket import KINDS, PRESETS, SCOPES, Spec, Target

EXIT_FAIL, EXIT_USAGE, EXIT_LOGIN, EXIT_STORE, EXIT_EXISTS, EXIT_ACCOUNT = 1, 2, 3, 5, 6, 7


def _say(msg: str) -> None:
    print(redact.scrub(msg))


def _target(args: argparse.Namespace) -> Target:
    target = Target(args.kind, args.workspace, args.repo, args.project_key)
    target.validate()
    return target


def _spec(args: argparse.Namespace) -> Spec:
    scopes = list(PRESETS[args.preset]) if args.preset else []
    for scope in (s.strip() for s in (args.scopes or "").split(",")):
        if scope and scope not in scopes:
            scopes.append(scope)
    spec = Spec(_target(args), args.name, scopes, args.expires)
    spec.validate()
    return spec


def _secret_ref(project: str, name: str) -> str:
    return f"projects/{project}/secrets/{name}"


def cmd_login(args: argparse.Namespace) -> int:
    from . import chrome

    chrome.open_for_login(args.url, dry_run=args.dry_run)
    if not args.dry_run:
        print(
            "A Chrome window opened on the tool's own profile.\n"
            "Sign in to Bitbucket with the account that administers the repositories,\n"
            "finish SSO and the second factor, then close that window.\n"
            "Next: `bab status`.",
            file=sys.stderr,
        )
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    from . import chrome

    chrome.start(dry_run=args.dry_run)
    if not args.dry_run:
        print(f"Chrome up on {config.CDP_URL} ({chrome.cdp_version().get('Browser')})")
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    from . import chrome

    print(chrome.stop())
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    from . import chrome, ui

    with chrome.attached() as page:
        page.goto(f"{config.BITBUCKET}/account/settings/", wait_until="domcontentloaded")
        ui.wait_idle(page, 2000)
        signed = not ui.is_login_page(page.url)
        session = account.signed_in(page) if signed else {}
        want = account.expected()
        print(f"profile:   {config.PROFILE_DIR}")
        print(f"cdp:       {config.CDP_URL}")
        print(f"signed in: {signed}")
        print(f"account:   {account.describe(session)}")
        print(f"expected:  {want or 'not configured (BAB_EXPECTED_ACCOUNT or BITBUCKET_EMAIL)'}")
        print(f"page:      {page.url}")
    if not signed:
        return EXIT_LOGIN
    return 0 if want and account.matches(session, want) else EXIT_ACCOUNT


def cmd_snap(args: argparse.Namespace) -> int:
    from . import chrome, snap

    with chrome.attached() as page:
        if args.url:
            page.goto(args.url, wait_until="domcontentloaded")
            page.wait_for_timeout(args.settle)
        out = snap.take(page, args.label)
        _say(snap.summary(page, out))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    from . import bitbucket, chrome

    target = _target(args)
    with chrome.attached() as page:
        names = bitbucket.existing_names(page, target)
    print(f"{target.label}: {len(names)} token(s)")
    for name in names:
        print(f"  {name}")
    return 0


@dataclass
class Dest:
    """One Secret Manager destination: project, secret, gcloud account, CMEK key."""
    project: str
    secret: str
    account: str | None
    exists: bool
    kms_key: str | None = None

    @property
    def ref(self) -> str:
        return _secret_ref(self.project, self.secret)


def _kms_for(project: str, specs: list[str] | None) -> str | None:
    """`PROJECT=KEY` entries win over a bare `KEY`, which applies to every project."""
    default = None
    for spec in specs or []:
        head, sep, tail = spec.partition("=")
        if sep and "/" not in head and not head.startswith("auto:"):
            if head == project:
                return tail
        else:
            default = spec
    return default


def _dests(projects: list[str], secret: str, args: argparse.Namespace,
           accounts: dict | None = None) -> list[Dest]:
    """Account, secret and KMS checks for every project, read-only, before any browser work."""
    out = []
    for project in projects:
        known = (accounts or {}).get(project)
        gcloud_account = known or sm.resolve_account(project, args.account, args.use_active_account)
        exists = sm.secret_exists(project, secret, gcloud_account)
        kms_key = None
        if not exists:
            if not args.create_secret:
                raise sm.SecretManagerError(
                    f"{_secret_ref(project, secret)} does not exist. Create it in the project's "
                    "IaC (labels, CMEK, IAM) or pass --create-secret (with --kms-key when the IaC "
                    "uses CMEK: Terraform replaces a secret whose replication differs)"
                )
            spec = _kms_for(project, args.kms_key)
            if spec:
                kms_key = sm.resolve_kms_key(project, spec, args.secret_locations, gcloud_account)
        out.append(Dest(project, secret, gcloud_account, exists, kms_key))
    return out


def _dest_line(d: Dest, args: argparse.Namespace) -> str:
    if d.exists:
        state = "exists, adds a new version"
    else:
        where = args.secret_locations or (sm.key_location(d.kms_key) if d.kms_key else None)
        enc = f"CMEK {d.kms_key}" if d.kms_key else "Google-managed key"
        state = f"missing, will be created in {where or 'automatic replication'}, {enc}"
    return f"  store    {d.ref} ({state})\n  gcloud   {d.account or 'active gcloud account'}"


def _plan(spec: Spec, args: argparse.Namespace, dests: list[Dest]) -> str:
    return "\n".join([
        "plan",
        f"  token    {spec.target.label}",
        f"  as       {args.expected_account or 'NOT CONFIGURED (pass --expected-account)'}",
        f"  name     {spec.name}",
        f"  scopes   {', '.join(spec.scopes)}",
        f"  expires  {spec.expires or 'workspace default (can be only 7 days: pass --expires)'}",
        *[_dest_line(d, args) for d in dests],
    ])


def _create_missing(dests: list[Dest], args: argparse.Namespace) -> None:
    for d in dests:
        if not d.exists:
            sm.create_secret(d.project, d.secret, d.account, args.secret_locations, d.kms_key)
            d.exists = True
            print(f"secret   created {d.ref}")


def _store(value: str, project: str, name: str, gcloud_account: str | None) -> str:
    version = sm.add_version(project, name, value, gcloud_account)
    if not sm.matches(sm.access(project, name, version, gcloud_account), value):
        raise sm.SecretManagerError(f"{version} does not match the token after read-back")
    return version


def _store_all(value: str, dests: list[Dest]) -> list[Dest]:
    """Store in every destination; returns the ones that failed."""
    failed = []
    for d in dests:
        try:
            version = _store(value, d.project, d.secret, d.account)
            print(f"store    {version} (read back, matches)")
        except sm.SecretManagerError as exc:
            _say(f"store    FAILED {d.ref}: {exc}")
            failed.append(d)
    return failed


def cmd_create(args: argparse.Namespace) -> int:
    from . import bitbucket, chrome, probe, snap, ui

    spec = _spec(args)
    args.expected_account = args.expected_account or account.expected()
    dests = _dests(args.gcp_project, args.secret_name, args)
    print(_plan(spec, args, dests))
    if not args.yes and not args.check_only:
        print("\nplan only: nothing created. Re-run with --yes once the plan is approved,"
              "\nor with --check-only to fill the form and cancel.")
        return 0
    if not args.expected_account:
        raise ValueError("no expected Atlassian account: set BITBUCKET_EMAIL in "
                         f"{account.ATLASSIAN_ENV} or pass --expected-account")

    with chrome.attached() as page:
        ui.goto(page, spec.target.settings_url)
        session = account.signed_in(page)
        if not account.matches(session, args.expected_account):
            print(f"\nthe browser is signed in as {account.describe(session)}, expected "
                  f"{args.expected_account}. Run `bab stop`, `bab login`, sign out and in "
                  "with the expected account, then run again.")
            return EXIT_ACCOUNT
        print(f"session  {account.describe(session)} (matches)")
        try:
            names = bitbucket.existing_names(page, spec.target)
            # Bitbucket refuses a second token with the same name ("A token with that
            # name already exists", 2026-10-23), so rotation needs a new name.
            hint = f"{spec.name}-{date.today():%Y%m%d}"
            if spec.name in names and args.check_only:
                print(f"note     a token named {spec.name!r} exists; --yes would stop here "
                      f"(rotate with a new name, e.g. {hint})")
            elif spec.name in names:
                print(f"\na token named {spec.name!r} already exists and Bitbucket refuses "
                      f"duplicate names. To rotate, create {hint!r}, let consumers pick up the "
                      "new secret version, then revoke the old token in Bitbucket.")
                return EXIT_EXISTS
            dialog = bitbucket.fill_form(page, spec)
            if args.check_only:
                out = snap.take(page, "check-only")
                bitbucket.cancel(page, dialog)
                print(f"\ncheck-only: form filled and cancelled, nothing created. Snapshot: {out}")
                return 0
            # Containers first: a refused secret must not leave a token behind.
            _create_missing(dests, args)
            created = bitbucket.submit(page, dialog)
        except Exception:
            out = snap.take(page, "create-failed")
            print(f"snapshot {out}", file=sys.stderr)
            raise
        meta = {
            "kind": spec.target.kind, "workspace": spec.target.workspace,
            "repo": spec.target.repo, "project_key": spec.target.project_key,
            "name": spec.name, "scopes": spec.scopes, "secret_name": args.secret_name,
            "gcp_projects": [d.project for d in dests],
            "accounts": {d.project: d.account for d in dests},
        }
        held = stash.write(created.value, meta)
        bitbucket.close_result(page)

    print(f"token    created ({spec.name})")
    if created.bot_email:
        print(f"git      user x-token-auth, commit email {created.bot_email}")
    ok, why = probe.check(spec.target, created.value)
    print(f"probe    {'OK ' if ok else 'BAD'} {why}")
    failed = _store_all(created.value, dests)
    if failed:
        projects = " ".join(f"--gcp-project {d.project}" for d in failed)
        print(f"stash    kept at {held} (mode 0600). Retry: bab push --stash '{held}' {projects} --yes")
        return EXIT_STORE
    if args.keep_stash:
        print(f"stash    kept at {held} (--keep-stash)")
    else:
        stash.remove(held)
        print("stash    removed")
    return 0 if ok else EXIT_FAIL


def cmd_push(args: argparse.Namespace) -> int:
    path = Path(args.stash).expanduser()
    value, meta = stash.read(path)
    projects = args.gcp_project or meta.get("gcp_projects") or [meta.get("gcp_project")]
    name = args.secret_name or meta.get("secret_name")
    if not all(projects) or not name:
        raise ValueError("the stash has no destination; pass --gcp-project and --secret-name")
    accounts = meta.get("accounts") or {p: meta.get("account") for p in projects if meta.get("account")}
    if args.account:
        accounts = {}
    dests = _dests(projects, name, args, accounts)
    print("plan\n" + "\n".join(_dest_line(d, args) for d in dests))
    if not args.yes:
        print("\nplan only: re-run with --yes once approved.")
        return 0
    _create_missing(dests, args)
    if _store_all(value, dests):
        return EXIT_STORE
    if not args.keep_stash:
        stash.remove(path)
        print("stash    removed")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from . import probe

    target = _target(args)
    worst = 0
    for project in args.gcp_project:
        gcloud_account = sm.resolve_account(project, args.account, args.use_active_account)
        value = sm.access(project, args.secret_name, args.version, gcloud_account).rstrip("\n")
        if not redact.contains(value):
            print(f"secret   {project}: does not look like a Bitbucket token (no ATCTT / ATATT prefix)")
        ok, why = probe.check(target, value, attempts=1)
        print(f"probe    {'OK ' if ok else 'BAD'} {why} "
              f"({_secret_ref(project, args.secret_name)}/versions/{args.version})")
        worst = worst if ok else EXIT_FAIL
    return worst


def _add_target(p: argparse.ArgumentParser) -> None:
    p.add_argument("--kind", choices=KINDS, default="repository")
    p.add_argument("--workspace", required=True, help="workspace slug")
    p.add_argument("--repo", help="repository slug (kind repository)")
    p.add_argument("--project-key", help="project key (kind project)")


def _add_store(p: argparse.ArgumentParser, required: bool = True) -> None:
    p.add_argument("--gcp-project", required=required, action="append",
                   help="GCP project id that holds the secret; repeat for several projects")
    p.add_argument("--secret-name", required=required, help="Secret Manager secret id")
    p.add_argument("--account", help="gcloud account (default: gcp-account.py map)")
    p.add_argument("--use-active-account", action="store_true",
                   help="fall back to the active gcloud account when the map has no match")


def _add_secret_creation(p: argparse.ArgumentParser) -> None:
    p.add_argument("--create-secret", action="store_true",
                   help="create the secret when missing (prefer IaC; match its replication)")
    p.add_argument("--secret-locations", default=os.environ.get("BAB_SECRET_LOCATIONS"),
                   help="user-managed replication, e.g. europe-west1 "
                        "(needed under a gcp.resourceLocations org policy)")
    p.add_argument("--kms-key", action="append",
                   default=[os.environ["BAB_KMS_KEY"]] if os.environ.get("BAB_KMS_KEY") else None,
                   help="CMEK for a created secret: a full cryptoKeys resource, or "
                        "auto:<keyring-glob>/<key> looked up per project in --secret-locations; "
                        "prefix PROJECT= to limit it to one project (repeatable)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bab", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="open plain Chrome on the tool profile to sign in once")
    p.add_argument("--url", default=f"{config.BITBUCKET}/account/signin/")
    p.add_argument("--dry-run", action="store_true", help="print the argv, launch nothing")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("start", help="start Chrome with the debugging port")
    p.add_argument("--dry-run", action="store_true", help="print the argv, launch nothing")
    p.set_defaults(func=cmd_start)
    sub.add_parser("stop", help="close the tool's Chrome").set_defaults(func=cmd_stop)
    sub.add_parser("status", help="is the profile signed in to Bitbucket?").set_defaults(func=cmd_status)

    p = sub.add_parser("snap", help="screenshot + accessibility tree of the current tab")
    p.add_argument("--url", help="navigate first")
    p.add_argument("--label", default="snap")
    p.add_argument("--settle", type=int, default=4000, help="ms to wait after navigating")
    p.set_defaults(func=cmd_snap)

    p = sub.add_parser("list", help="names of the access tokens on a repo, project or workspace")
    _add_target(p)
    p.set_defaults(func=cmd_list)

    presets = "; ".join(f"{k} = {', '.join(v)}" for k, v in PRESETS.items())
    p = sub.add_parser("create", help="create a token and store it in Secret Manager",
                       epilog=f"scopes: {', '.join(SCOPES)}. presets: {presets}")
    _add_target(p)
    p.add_argument("--name", required=True, help="token name shown in Bitbucket")
    p.add_argument("--expected-account",
                   help="Atlassian email or account id the browser must be signed in as "
                        "(default: BAB_EXPECTED_ACCOUNT, BITBUCKET_EMAIL, JIRA_EMAIL)")
    p.add_argument("--preset", choices=sorted(PRESETS),
                   help="read: clone/pull; admin: Cloud Build connection + Renovate PRs")
    p.add_argument("--scopes", help="comma-separated, added to the preset, e.g. repository,pullrequest")
    p.add_argument("--expires", help="YYYY-MM-DD, at most 365 days ahead")
    _add_store(p)
    _add_secret_creation(p)
    p.add_argument("--check-only", action="store_true", help="fill the form, snapshot, cancel")
    p.add_argument("--keep-stash", action="store_true", help="keep the local 0600 copy")
    p.add_argument("--yes", action="store_true", help="act; without it only the plan is printed")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("push", help="store a stashed token (after a failed create)")
    p.add_argument("--stash", required=True)
    _add_store(p, required=False)
    _add_secret_creation(p)
    p.add_argument("--keep-stash", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_push)

    p = sub.add_parser("verify", help="check a stored token against the Bitbucket API")
    _add_target(p)
    _add_store(p)
    p.add_argument("--version", default="latest")
    p.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        _say(f"error: {exc}")
        return EXIT_USAGE
    except sm.SecretManagerError as exc:
        _say(f"secret manager: {exc}")
        return EXIT_STORE if args.cmd == "push" else EXIT_FAIL
    except ImportError as exc:
        print(f"error: {exc}. Run `tools/bitbucket-access-bootstrap/bin/bab install`.", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:
        from .ui import NotSignedIn

        if isinstance(exc, NotSignedIn):
            _say(f"NOT SIGNED IN: {exc}")
            return EXIT_LOGIN
        _say(f"error: {type(exc).__name__}: {exc}")
        return EXIT_FAIL
