#!/usr/bin/env python3
"""gmail.py: read your Gmail as yourself. READ-ONLY by construction.

    kit/bundles/google/scripts/gmail.py login
    kit/bundles/google/scripts/gmail.py whoami
    kit/bundles/google/scripts/gmail.py search 'from:billing@example.com newer_than:3m' --limit 20
    kit/bundles/google/scripts/gmail.py get <message-id>          # headers + plain-text body
    kit/bundles/google/scripts/gmail.py thread <thread-id>
    kit/bundles/google/scripts/gmail.py attachments <message-id> --out DIR

The only scope requested is gmail.readonly: nothing here can send, delete, label or
modify mail. <query> is Gmail search syntax (from:, to:, subject:, has:attachment,
after:2026/01/01, newer_than:3m, filename:pdf).
Credentials: lib/google_oauth.py (token in ~/.config/agent-skeleton/google/gmail-token.json).
Python 3.9+, standard library only.
"""

import argparse
import base64
import html
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
import google_oauth as go  # noqa: E402

TOOL = "gmail"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
MAILBOX = "me"                     # the authenticated user
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def api(path, params=None):
    status, payload = go.request("GET", "%s/%s/%s/%s" % (GMAIL_API, "users", MAILBOX,
                                                          path.lstrip("/")),
                                 go.access_token(TOOL), params=params)
    return go.check(status, payload)


def b64(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def headers_of(msg):
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def strip_html(text):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _walk(part, out):
    mime = part.get("mimeType", "")
    body = part.get("body", {})
    if part.get("filename"):
        out["attachments"].append({"filename": part["filename"], "mimeType": mime,
                                   "size": body.get("size", 0),
                                   "attachmentId": body.get("attachmentId")})
    elif mime == "text/plain" and body.get("data"):
        out["plain"].append(b64(body["data"]).decode("utf-8", "replace"))
    elif mime == "text/html" and body.get("data"):
        out["html"].append(b64(body["data"]).decode("utf-8", "replace"))
    for sub in part.get("parts", []) or []:
        _walk(sub, out)


def message_text(msg):
    """(plain text body, attachments). HTML-only mail is converted to text."""
    out = {"plain": [], "html": [], "attachments": []}
    _walk(msg.get("payload", {}), out)
    text = "\n".join(out["plain"]).strip() or strip_html("\n".join(out["html"]))
    return text, out["attachments"]


def summarize(msg):
    h = headers_of(msg)
    return {"id": msg["id"], "threadId": msg.get("threadId"), "date": h.get("date", ""),
            "from": h.get("from", ""), "to": h.get("to", ""), "subject": h.get("subject", ""),
            "snippet": html.unescape(msg.get("snippet", ""))}


def safe_name(name, fallback):
    """An attachment file name that cannot escape the output directory."""
    base = os.path.basename((name or "").replace("\\", "/")).strip().lstrip(".")
    return re.sub(r"[\x00-\x1f]", "_", base) or fallback


# ---------------------------------------------------------------------------- commands
def cmd_login(args):
    return go.run_login(TOOL, SCOPES, args, must_have=SCOPES)


def cmd_logout(args):
    print("logged out" if go.logout(TOOL, revoke=not args.keep_grant) else "not logged in")


def cmd_whoami(args):
    prof = api("profile")
    if not go.emit(prof, args.json):
        print("%s  messages=%s  threads=%s" % (prof.get("emailAddress"), prof.get("messagesTotal"),
                                               prof.get("threadsTotal")))


def cmd_search(args):
    ids, token = [], None
    while len(ids) < args.limit:
        params = {"q": args.query, "maxResults": min(500, args.limit - len(ids))}
        if args.include_spam_trash:
            params["includeSpamTrash"] = "true"
        if token:
            params["pageToken"] = token
        page = api("messages", params)
        ids += [m["id"] for m in page.get("messages", [])]
        token = page.get("nextPageToken")
        if not token:
            break
    rows = [summarize(api("messages/%s" % i, {"format": "metadata",
                                              "metadataHeaders": ["From", "To", "Subject", "Date"]}))
            for i in ids]
    if go.emit(rows, args.json):
        return
    for r in rows:
        print("%s  %-31s  %-40s  %s" % (r["id"], r["date"][:31], r["from"][:40], r["subject"]))
    sys.stderr.write("\n%d message(s)\n" % len(rows))


def _render(msg, as_json):
    text, atts = message_text(msg)
    meta = summarize(msg)
    if as_json:
        return dict(meta, body=text, attachments=atts)
    print("Date:    %s\nFrom:    %s\nTo:      %s\nSubject: %s\nId:      %s  thread %s" % (
        meta["date"], meta["from"], meta["to"], meta["subject"], meta["id"], meta["threadId"]))
    for a in atts:
        print("Attach:  %s (%s, %s B)" % (a["filename"], a["mimeType"], a["size"]))
    print("\n" + text + "\n")
    return None


def cmd_get(args):
    obj = _render(api("messages/%s" % args.id, {"format": "full"}), args.json)
    if obj is not None:
        go.emit(obj, True)


def cmd_thread(args):
    th = api("threads/%s" % args.id, {"format": "full"})
    objs = []
    for msg in th.get("messages", []):
        obj = _render(msg, args.json)
        if obj is not None:
            objs.append(obj)
        elif not args.json:
            print("-" * 72)
    if args.json:
        go.emit(objs, True)


def cmd_attachments(args):
    msg = api("messages/%s" % args.id, {"format": "full"})
    _, atts = message_text(msg)
    os.makedirs(args.out, exist_ok=True)
    for a in atts:
        if not a.get("attachmentId"):
            continue
        data = api("messages/%s/attachments/%s" % (args.id, a["attachmentId"])).get("data", "")
        path = os.path.join(args.out, safe_name(a["filename"], a["attachmentId"]))
        with open(path, "wb") as fh:
            fh.write(b64(data))
        print(path)


def cmd_token(_args):
    print(go.access_token(TOOL))


def build_parser():
    p = argparse.ArgumentParser(prog="gmail.py", description="Read Gmail as yourself (read-only).")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    def add(name, fn, help_text, json_flag=True):
        sp = sub.add_parser(name, help=help_text)
        if json_flag:
            sp.add_argument("--json", action="store_true", help="raw JSON output")
        sp.set_defaults(func=fn)
        return sp

    go.add_login_args(add("login", cmd_login, "browser OAuth flow (gmail.readonly only)", False))
    add("logout", cmd_logout, "forget (and revoke) the token", False).add_argument(
        "--keep-grant", action="store_true", help="delete locally, do not revoke at Google")
    add("whoami", cmd_whoami, "mailbox address and totals")
    sp = add("search", cmd_search, "search with Gmail query syntax")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--include-spam-trash", action="store_true")
    add("get", cmd_get, "one message: headers and text body").add_argument("id")
    add("thread", cmd_thread, "every message of a thread").add_argument("id")
    sp = add("attachments", cmd_attachments, "download a message's attachments", False)
    sp.add_argument("id")
    sp.add_argument("--out", required=True)
    add("token", cmd_token, "print a fresh bearer token", False)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    go.main_guard(main)
