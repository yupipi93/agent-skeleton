"""Command line entry point.

Exit codes: 0 ok (or plan printed), 1 a step failed, 2 bad usage or an incomplete
request, 3 not signed in, 5 blocked by the text guard, 6 an open request of the same
type already exists, 7 the browser is signed in as another account than the expected one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import catalog, config, portal

EXIT_FAIL, EXIT_USAGE, EXIT_LOGIN, EXIT_GUARD, EXIT_DUPLICATE, EXIT_ACCOUNT = 1, 2, 3, 5, 6, 7


def _who(me: dict) -> str:
    email = me.get("emailAddress") or me.get("email") or ""
    return f"{me.get('displayName', '?')} <{email or 'email hidden'}> {me.get('accountId', '')}".strip()


def _account_ok(me: dict, want: str) -> bool:
    if not want:
        return True
    want = want.strip().lower()
    return want in {str(me.get(k, "")).lower() for k in ("accountId", "emailAddress", "email", "name")}


def _check_account(session: portal.Session, override: str | None) -> dict:
    me = session.myself()
    want = override or config.expected_account()
    if not _account_ok(me, want):
        print(f"jpr: signed in as {_who(me)}, expected {want}. Run `jpr stop`, then `jpr login` "
              "and sign in with the right account.", file=sys.stderr)
        raise SystemExit(EXIT_ACCOUNT)
    return me


def cmd_login(args) -> int:
    from . import chrome

    url = args.url or f"{config.base_url()}/servicedesk/customer/portals"
    chrome.open_for_login(url, dry_run=args.dry_run)
    if not args.dry_run:
        print("A Chrome window opened on the tool's own profile.\n"
              "Sign in with the account that should raise the requests, finish SSO and the\n"
              "second factor, then close that window. Next: `jpr status`.", file=sys.stderr)
    return 0


def cmd_start(args) -> int:
    from . import chrome

    chrome.start(dry_run=args.dry_run)
    if not args.dry_run:
        print(f"Chrome up on {config.CDP_URL} ({chrome.cdp_version().get('Browser')})")
    return 0


def cmd_stop(_) -> int:
    from . import chrome

    print(chrome.stop())
    return 0


def cmd_status(args) -> int:
    from . import chrome

    with chrome.attached() as page:
        session = portal.Session(page)
        me = session.myself()
    want = args.expected_account or config.expected_account()
    print(f"site:      {config.site()}")
    print(f"profile:   {config.PROFILE_DIR}")
    print(f"account:   {_who(me)}")
    print(f"expected:  {want or 'not configured (JPR_EXPECTED_ACCOUNT)'}")
    return 0 if _account_ok(me, want) else EXIT_ACCOUNT


def cmd_snap(args) -> int:
    from . import chrome, snap

    with chrome.attached() as page:
        if args.url:
            portal.goto(page, args.url)
        out = snap.take(page, args.label)
        print(snap.summary(page, out))
    return 0


def cmd_crawl(args) -> int:
    from . import chrome

    only = set(args.portal or []) or None
    with chrome.attached() as page:
        _check_account(portal.Session(page), args.expected_account)
        data = catalog.crawl(page, only, ui=args.ui, log=lambda m: print(m, file=sys.stderr))
    n_types = sum(len(p["requestTypes"]) for p in data["portals"])
    print(f"catalog   {catalog.catalog_path()}")
    print(f"markdown  {catalog.site_dir() / 'index.md'}")
    print(f"portals   {len(data['portals'])}, request types {n_types}")
    return 0


def cmd_portals(_) -> int:
    data = catalog.load()
    print(f"# {data['site']}, crawled {data['crawledAt']}")
    for p in data["portals"]:
        print(f"{p['serviceDeskId']:>5}  {p['projectKey']:<12} {p['name']}  "
              f"({len(p['groups'])} categories, {len(p['requestTypes'])} types)")
    return 0


def cmd_types(args) -> int:
    data = catalog.load()
    p = catalog.find_portal(data, args.portal)
    print(f"# {p['name']} (service desk {p['serviceDeskId']})")
    for g in p["groups"] + [{"id": None, "name": "(no category)"}]:
        rts = [rt for rt in p["requestTypes"] if (g["id"] in rt["groupIds"] if g["id"] else not rt["groupIds"])]
        if not rts:
            continue
        print(f"\n{g['name']}")
        for rt in rts:
            print(f"  {rt['id']:>5}  {rt['name']}")
    return 0


def cmd_show(args) -> int:
    data = catalog.load()
    p = catalog.find_portal(data, args.portal)
    rt = catalog.find_type(p, args.type)
    if args.json:
        print(json.dumps(rt, indent=2, ensure_ascii=False))
    else:
        print("\n".join(catalog.render_type(p, rt)))
    return 0


def _pairs(args) -> list[tuple[str, str]]:
    pairs = []
    for item in args.field or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise SystemExit(f"jpr: --field wants NAME=VALUE, got '{item}'")
        if value.startswith("@"):
            value = Path(value[1:]).expanduser().read_text().rstrip("\n")
        pairs.append((key.strip(), value))
    if args.summary:
        pairs.append(("summary", args.summary))
    if args.description_file:
        pairs.append(("description", Path(args.description_file).expanduser().read_text().rstrip("\n")))
    elif args.description:
        pairs.append(("description", args.description))
    return pairs


def cmd_request(args) -> int:
    from . import request

    data = catalog.load()
    p = catalog.find_portal(data, args.portal)
    rt = catalog.find_type(p, args.type)
    plan = request.build(p, rt, _pairs(args), args.participant or [], args.on_behalf_of or "")
    print(request.render(plan))
    ok, msg = request.guard(plan.texts())
    if not ok:
        print(f"BLOCKED   text guard: {msg}", file=sys.stderr)
        return EXIT_GUARD
    if plan.problems:
        return EXIT_USAGE
    if args.json:
        print(json.dumps(plan.payload(), indent=2, ensure_ascii=False))
    if not args.yes:
        print("\nplan only: nothing sent. Re-run with --yes to raise it.")
        return 0

    from . import chrome

    with chrome.attached() as page:
        session = portal.Session(page)
        me = _check_account(session, args.expected_account)
        open_same = session.paged(
            "/rest/servicedeskapi/request?requestOwnership=OWNED_REQUESTS&requestStatus=OPEN_REQUESTS"
            f"&serviceDeskId={p['serviceDeskId']}&requestTypeId={rt['id']}", limit=50)
        if open_same and not args.allow_duplicate:
            print(f"\nSTOP      this account already has {len(open_same)} open '{rt['name']}' request(s):")
            for r in open_same:
                summary = next((v.get("value") for v in r.get("requestFieldValues", [])
                                if v.get("fieldId") == "summary"), "")
                print(f"          {r['issueKey']}  {summary}")
            print("          Check they are not the same request; re-run with --allow-duplicate if not.")
            return EXIT_DUPLICATE
        created = session.call("POST", "/rest/servicedeskapi/request", plan.payload())
    key = created.get("issueKey", "?")
    record = config.RUNS_DIR / f"request-{key}.json"
    record.write_text(json.dumps({"payload": plan.payload(), "response": created}, indent=2, ensure_ascii=False))
    print(f"\ncreated   {key} as {_who(me)}")
    print(f"link      {request.portal_link(p['portalId'], key)}")
    status = (created.get("currentStatus") or {}).get("status")
    if status:
        print(f"status    {status}")
    return 0


def cmd_mine(args) -> int:
    from . import chrome

    params = {"requestOwnership": "OWNED_REQUESTS", "requestStatus": "ALL_REQUESTS" if args.all else "OPEN_REQUESTS"}
    with chrome.attached() as page:
        session = portal.Session(page)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        rows = session.paged(f"/rest/servicedeskapi/request?{query}&expand=requestType", limit=50)
    for r in rows:
        status = (r.get("currentStatus") or {}).get("status", "?")
        rt = (r.get("requestType") or {}).get("name", "?")
        summary = next((v.get("value") for v in r.get("requestFieldValues", []) if v.get("fieldId") == "summary"), "")
        print(f"{r['issueKey']:<14} {status:<22} {rt:<36} {summary}")
    return 0


def cmd_get(args) -> int:
    from . import chrome

    with chrome.attached() as page:
        session = portal.Session(page)
        r = session.get(f"/rest/servicedeskapi/request/{args.key}?expand=requestType,status,participant")
        comments = session.paged(f"/rest/servicedeskapi/request/{args.key}/comment?public=true&internal=false")
    print(f"{r['issueKey']}  {(r.get('currentStatus') or {}).get('status', '?')}  "
          f"{(r.get('requestType') or {}).get('name', '?')}")
    print(f"reporter  {(r.get('reporter') or {}).get('displayName', '?')}")
    print(f"created   {(r.get('createdDate') or {}).get('friendly', '?')}")
    for v in r.get("requestFieldValues", []):
        val = v.get("value")
        if isinstance(val, dict):
            val = val.get("value") or val.get("name") or json.dumps(val, ensure_ascii=False)
        elif isinstance(val, list):
            val = "; ".join(str(x.get("value") or x.get("name") or x) if isinstance(x, dict) else str(x) for x in val)
        print(f"{v.get('label', v.get('fieldId'))}: {val}")
    for c in comments:
        print(f"\n--- {(c.get('author') or {}).get('displayName', '?')}, {(c.get('created') or {}).get('friendly', '')}")
        print(c.get("body", ""))
    return 0


def cmd_comment(args) -> int:
    from . import chrome, request

    text = Path(args.file).expanduser().read_text() if args.file else args.text
    if not text or not text.strip():
        raise SystemExit("jpr: comment needs --text or --file")
    ok, msg = request.guard(text)
    if not ok:
        print(f"BLOCKED   text guard: {msg}", file=sys.stderr)
        return EXIT_GUARD
    print(f"comment on {args.key} (public):\n{text}")
    if not args.yes:
        print("\nplan only: nothing sent. Re-run with --yes to post it.")
        return 0
    with chrome.attached() as page:
        session = portal.Session(page)
        _check_account(session, args.expected_account)
        c = session.call("POST", f"/rest/servicedeskapi/request/{args.key}/comment", {"body": text, "public": True})
    print(f"posted    comment {c.get('id')} on {args.key}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="jpr", description="Jira Service Management customer portal requests, "
                                 "raised as the person signed in to the tool's Chrome.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login", help="plain Chrome on the tool profile, for a human sign-in")
    s.add_argument("--url")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("start", help="Chrome with the debugging port")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_start)

    sub.add_parser("stop", help="close the tool's Chrome").set_defaults(func=cmd_stop)

    s = sub.add_parser("status", help="which account the portal session belongs to")
    s.add_argument("--expected-account")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("snap", help="URL, accessibility tree and screenshot of the tab")
    s.add_argument("--url")
    s.add_argument("--label", default="snap")
    s.set_defaults(func=cmd_snap)

    s = sub.add_parser("crawl", help="walk the portals and write the catalog")
    s.add_argument("--portal", action="append", help="service desk id or project key (repeatable); default all")
    s.add_argument("--ui", action="store_true", help="also open every portal, category and create form")
    s.add_argument("--expected-account")
    s.set_defaults(func=cmd_crawl)

    sub.add_parser("portals", help="portals in the catalog").set_defaults(func=cmd_portals)

    s = sub.add_parser("types", help="categories and request types of a portal")
    s.add_argument("portal", help="service desk id, project key or name")
    s.set_defaults(func=cmd_types)

    s = sub.add_parser("show", help="fields of one request type")
    s.add_argument("portal")
    s.add_argument("type", help="request type id or name")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("request", help="plan, then (--yes) raise a request")
    s.add_argument("portal")
    s.add_argument("type")
    s.add_argument("--summary")
    s.add_argument("--description")
    s.add_argument("--description-file")
    s.add_argument("--field", action="append", metavar="NAME=VALUE",
                   help="field id or label; VALUE may be @file, json:<raw>, 'A; B' for lists, 'Parent > Child'")
    s.add_argument("--participant", action="append", metavar="ACCOUNT_ID")
    s.add_argument("--on-behalf-of", metavar="ACCOUNT_ID")
    s.add_argument("--json", action="store_true", help="also print the payload")
    s.add_argument("--expected-account")
    s.add_argument("--allow-duplicate", action="store_true",
                   help="send even when an open request of the same type exists")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_request)

    s = sub.add_parser("mine", help="requests raised by the signed-in account")
    s.add_argument("--all", action="store_true", help="closed ones too")
    s.set_defaults(func=cmd_mine)

    s = sub.add_parser("get", help="one request with its public comments")
    s.add_argument("key")
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("comment", help="plan, then (--yes) add a public comment")
    s.add_argument("key")
    s.add_argument("--text")
    s.add_argument("--file")
    s.add_argument("--expected-account")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_comment)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except portal.NotSignedIn as exc:
        print(f"jpr: {exc}", file=sys.stderr)
        return EXIT_LOGIN
    except portal.ApiError as exc:
        print(f"jpr: {exc}", file=sys.stderr)
        return EXIT_FAIL
    except (RuntimeError, TimeoutError) as exc:
        print(f"jpr: {exc}", file=sys.stderr)
        return EXIT_FAIL
