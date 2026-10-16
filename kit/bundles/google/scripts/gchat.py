#!/usr/bin/env python3
"""gchat.py: read and write Google Chat as yourself, through the GA Chat REST API.

    kit/bundles/google/scripts/gchat.py login                       # once, opens the browser
    kit/bundles/google/scripts/gchat.py whoami
    kit/bundles/google/scripts/gchat.py spaces --type SPACE --name "release"
    kit/bundles/google/scripts/gchat.py find-dm someone@example.com
    kit/bundles/google/scripts/gchat.py messages spaces/AAAA1234 --limit 20
    kit/bundles/google/scripts/gchat.py send spaces/AAAA1234 --text "hello" [--dry-run]
    kit/bundles/google/scripts/gchat.py search --keywords release notes --days 30
    kit/bundles/google/scripts/gchat.py probe-write spaces/AAAA1234   # posts nothing

Messages are sent as you (user OAuth, sender.type HUMAN): there is no bot identity.
Credentials: lib/google_oauth.py (your client.json, a refresh token in
~/.config/agent-skeleton/google/gchat-token.json, 0600). Chat needs a Google Workspace
account and a configured Chat app in the Cloud project; see docs/bundles/google.md.
Python 3.9+, standard library only.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
import google_oauth as go  # noqa: E402

TOOL = "gchat"
API = "https://chat.googleapis.com/v1"
SCOPES = [
    "https://www.googleapis.com/auth/chat.spaces",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.memberships.readonly",
    "https://www.googleapis.com/auth/chat.messages",
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.messages.create",
]


def api(path, method="GET", params=None, body=None):
    status, payload = go.request(method, "%s/%s" % (API, path.lstrip("/")),
                                 go.access_token(TOOL), params=params, body=body)
    return go.check(status, payload)


def paged(path, key, params=None, limit=None):
    params = dict(params or {})
    out = []
    while True:
        page = api(path, params=params)
        out.extend(page.get(key, []))
        token = page.get("nextPageToken")
        if not token or (limit and len(out) >= limit):
            break
        params["pageToken"] = token
    return out[:limit] if limit else out


def markdown_lines(text):
    """Keep line breaks visible under MARKUP_SYNTAX_MARKDOWN.

    Markdown treats one newline as a soft break, so stacked one-idea lines collapse into
    one paragraph. Bullet lines become real "- " list items; other line breaks get a blank
    line, which Chat renders as a break.
    """
    out = []
    for line in text.rstrip("\n").split("\n"):
        bullet = line.lstrip().startswith(("• ", "- ", "* "))
        if bullet:
            line = "- " + line.lstrip()[2:]
        prev = out[-1] if out else ""
        if prev.strip() and line.strip() and not (bullet and prev.startswith("- ")):
            out.append("")
        out.append(line)
    return "\n".join(out)


def send_body(text, thread=None):
    """The messages.create body. markupSyntax is explicit on purpose: when it is omitted,
    the API accepts *bold* and silently never parses it (text == formattedText)."""
    if "```" not in text:
        text = markdown_lines(text)
    body = {"text": text, "markupSyntax": "MARKUP_SYNTAX_MARKDOWN"}
    if thread:
        body["thread"] = {"name": thread}
    return body


# ---------------------------------------------------------------------------- commands
def resolve_me():
    """There is no 'get my user id' endpoint: intersect the human members of a few DMs."""
    spaces = paged("spaces", "spaces", {"pageSize": 100}, limit=100)
    dms = [s["name"] for s in spaces if s.get("spaceType") == "DIRECT_MESSAGE"][:5]
    if not dms:
        raise go.OAuthError("no DM spaces to derive your user id from")
    sets = []
    for name in dms:
        members = api("%s/members" % name, params={"pageSize": 10}).get("memberships", [])
        sets.append({m["member"]["name"] for m in members
                     if m.get("member", {}).get("type") == "HUMAN"})
    common = set.intersection(*sets)
    if len(common) != 1:
        raise go.OAuthError("could not single out your user id (candidates: %d)" % len(common))
    return common.pop()


def cmd_login(args):
    return go.run_login(TOOL, SCOPES, args,
                        must_have=["https://www.googleapis.com/auth/chat.messages.create"])


def cmd_logout(args):
    print("logged out" if go.logout(TOOL, revoke=not args.keep_grant) else "not logged in")


def cmd_whoami(args):
    me = resolve_me()
    if not go.emit({"user": me}, args.json):
        print(me)


def cmd_spaces(args):
    spaces = paged("spaces", "spaces", {"pageSize": 100})     # filter first, then truncate
    if args.type:
        spaces = [s for s in spaces if s.get("spaceType") == args.type]
    if args.name:
        needle = args.name.lower()
        spaces = [s for s in spaces if needle in (s.get("displayName") or "").lower()]
    spaces = spaces[:args.limit]
    if go.emit(spaces, args.json):
        return
    print("%d spaces" % len(spaces))
    for s in spaces:
        print("  %-15s %-28s %s" % (s.get("spaceType", "?"), s["name"],
                                    s.get("displayName") or "(DM)"))


def cmd_members(args):
    members = paged("%s/members" % args.space, "memberships", {"pageSize": 100})
    if go.emit(members, args.json):
        return
    for m in members:
        member = m.get("member", {})
        print("  %-6s %-32s %s" % (member.get("type", "?"), member.get("name", "?"),
                                   member.get("displayName") or ""))


def cmd_find_dm(args):
    res = api("spaces:findDirectMessage", params={"name": "users/%s" % args.email})
    if not go.emit(res, args.json):
        print(res["name"])


def cmd_messages(args):
    params = {"pageSize": min(args.limit, 100), "orderBy": "createTime desc"}
    if args.since:
        params["filter"] = 'createTime > "%s"' % args.since
    msgs = paged("%s/messages" % args.space, "messages", params, limit=args.limit)
    msgs.reverse()
    if go.emit(msgs, args.json):
        return
    me = resolve_me() if args.mark_me else None
    for m in msgs:
        sender = m.get("sender", {}).get("name", "?")
        who = "ME" if sender == me else sender.replace("users/", "")
        stamp = (m.get("createTime") or "")[:19].replace("T", " ")
        text = (m.get("text") or "<no text / attachment>").replace("\n", "\n      ")
        print("[%s] %s: %s" % (stamp, who, text))


def read_text_arg(args):
    if args.text_file:
        if args.text_file == "-":
            return sys.stdin.read()
        with open(args.text_file, encoding="utf-8") as fh:
            return fh.read()
    return args.text or ""


def cmd_send(args):
    text = read_text_arg(args)
    if not text.strip():
        raise go.OAuthError("need --text or --text-file")
    body = send_body(text, args.thread)
    params = {"messageReplyOption": "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"} if args.thread else None
    if args.dry_run:
        go.emit({"space": args.space, "params": params, "body": body}, True)
        return
    res = api("%s/messages" % args.space, method="POST", params=params, body=body)
    if go.emit(res, args.json):
        return
    print("sent: %s" % res["name"])
    print("thread: %s" % res.get("thread", {}).get("name"))


def cmd_probe_write(args):
    """Prove posting rights without posting: an invalid messageId fails validation (400)
    only after the permission check. Chat answers 403 for both 'denied' and 'no such
    space', so a 403 alone proves nothing about existence."""
    status, payload = go.request("POST", "%s/%s/messages" % (API, args.space),
                                 go.access_token(TOOL), params={"messageId": "invalid-format"},
                                 body={"text": "probe"})
    err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
    if status == 400:
        verdict = "WRITE OK: rejected at validation, so authorization passed (nothing posted)"
    elif status == 403:
        verdict = "DENIED OR MISSING: Chat returns 403 for both; check the space id and membership"
    elif status == 404:
        verdict = "NOT FOUND"
    elif status < 300:
        verdict = "UNEXPECTED: the API accepted the probe; check the space"
    else:
        verdict = "UNEXPECTED: see status and message"
    out = {"space": args.space, "httpCode": status, "status": err.get("status", ""),
           "message": err.get("message", ""), "verdict": verdict}
    if not go.emit(out, args.json):
        print("HTTP %s %s\n%s" % (status, out["status"], verdict))


def cmd_search(args):
    """Brute-force keyword search: the REST API has no message search."""
    spaces = paged("spaces", "spaces", {"pageSize": 100}, limit=args.spaces)
    if args.space_name:
        needle = args.space_name.lower()
        spaces = [s for s in spaces if needle in (s.get("displayName") or "").lower()]
    since = None
    if args.days:
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - args.days * 86400))
    words = [w.lower() for w in args.keywords]
    hits = []
    for idx, sp in enumerate(spaces, 1):
        if not args.json:
            sys.stderr.write("\rscanning %d/%d %-28s" % (idx, len(spaces), sp["name"]))
        params = {"pageSize": 100}
        if since:
            params["filter"] = 'createTime > "%s"' % since
        try:
            msgs = paged("%s/messages" % sp["name"], "messages", params, limit=args.per_space)
        except go.OAuthError:
            continue
        for m in msgs:
            text = m.get("text") or ""
            if all(w in text.lower() for w in words):
                if args.sender and m.get("sender", {}).get("name") != args.sender:
                    continue
                hits.append({"space": sp["name"], "spaceName": sp.get("displayName") or "(DM)",
                             "createTime": m.get("createTime"),
                             "sender": m.get("sender", {}).get("name"), "text": text,
                             "message": m.get("name")})
    if not args.json:
        sys.stderr.write("\r" + " " * 60 + "\r")
    hits.sort(key=lambda h: h.get("createTime") or "")
    if go.emit(hits, args.json):
        return
    print("%d matches" % len(hits))
    for h in hits:
        print("\n[%s] %s (%s)\n  %s" % ((h["createTime"] or "")[:19].replace("T", " "),
                                       h["spaceName"], h["space"], h["text"][:400]))


def cmd_create_space(args):
    body = {"spaceType": "SPACE", "displayName": args.name}
    if args.description:
        body["spaceDetails"] = {"description": args.description}
    res = api("spaces", method="POST", body=body)
    if not go.emit(res, args.json):
        print("created: %s (%s)" % (res["name"], res.get("displayName")))


def cmd_scopes(args):
    info = go.tokeninfo(go.access_token(TOOL))
    granted = sorted(info.get("scope", "").split())
    if not go.emit({"expires_in": info.get("expires_in"), "scopes": granted}, args.json):
        for s in granted:
            print("  %s" % s)


def cmd_token(_args):
    """A bearer token for one-off requests this script does not wrap (stdout only)."""
    print(go.access_token(TOOL))


def build_parser():
    p = argparse.ArgumentParser(prog="gchat.py", description="Google Chat as yourself.")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    def add(name, fn, help_text, json_flag=True):
        sp = sub.add_parser(name, help=help_text)
        if json_flag:
            sp.add_argument("--json", action="store_true", help="raw JSON output")
        sp.set_defaults(func=fn)
        return sp

    go.add_login_args(add("login", cmd_login, "browser OAuth flow; stores a refresh token", False))
    add("logout", cmd_logout, "forget (and revoke) the token", False).add_argument(
        "--keep-grant", action="store_true", help="delete locally, do not revoke at Google")
    add("whoami", cmd_whoami, "your Chat user id")
    sp = add("spaces", cmd_spaces, "list spaces")
    sp.add_argument("--type", choices=["SPACE", "DIRECT_MESSAGE", "GROUP_CHAT"])
    sp.add_argument("--name", help="display name substring")
    sp.add_argument("--limit", type=int, default=200)
    add("members", cmd_members, "members of a space").add_argument("space")
    add("find-dm", cmd_find_dm, "the 1:1 DM with someone").add_argument("email")
    sp = add("messages", cmd_messages, "read a space, oldest first")
    sp.add_argument("space")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--since", help="RFC3339, e.g. 2026-01-01T00:00:00Z")
    sp.add_argument("--mark-me", action="store_true", help="label your own messages as ME")
    sp = add("send", cmd_send, "send a message as you")
    sp.add_argument("space")
    sp.add_argument("--text")
    sp.add_argument("--text-file", help="file, or - for stdin")
    sp.add_argument("--thread", help="spaces/X/threads/Y to reply in-thread")
    sp.add_argument("--dry-run", action="store_true", help="print the request, send nothing")
    add("probe-write", cmd_probe_write, "prove posting rights without posting").add_argument("space")
    sp = add("search", cmd_search, "keyword search across spaces (slow)")
    sp.add_argument("--keywords", nargs="+", required=True)
    sp.add_argument("--sender", help="users/ID")
    sp.add_argument("--days", type=int)
    sp.add_argument("--spaces", type=int, default=100, help="max spaces to scan")
    sp.add_argument("--per-space", type=int, default=200, help="max messages per space")
    sp.add_argument("--space-name", help="only spaces whose name contains this")
    sp = add("create-space", cmd_create_space, "create a named space")
    sp.add_argument("--name", required=True)
    sp.add_argument("--description")
    add("scopes", cmd_scopes, "what the stored token can do")
    add("token", cmd_token, "print a fresh bearer token", False)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    go.main_guard(main)
