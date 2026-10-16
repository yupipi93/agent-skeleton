#!/usr/bin/env python3
"""gdocs.py: find, read and edit Google Docs as yourself (Docs + Drive REST APIs).

    kit/bundles/google/scripts/gdocs.py login
    kit/bundles/google/scripts/gdocs.py search --name "roadmap"
    kit/bundles/google/scripts/gdocs.py search --content "release checklist" --limit 10
    kit/bundles/google/scripts/gdocs.py info <doc>
    kit/bundles/google/scripts/gdocs.py get <doc>                       # plain text
    kit/bundles/google/scripts/gdocs.py export <doc> --format md --out notes.md
    kit/bundles/google/scripts/gdocs.py create --title "Scratch" --text "hello"
    kit/bundles/google/scripts/gdocs.py append <doc> --text "one more line"
    kit/bundles/google/scripts/gdocs.py replace <doc> --find OLD --replace NEW
    kit/bundles/google/scripts/gdocs.py probe-write <doc>               # changes nothing

<doc> is a document id or any Google Docs URL. Drive finds, exports and describes files;
Docs reads and edits one document's content; each command routes itself.

Every edit is attributed to you in the revision history (user OAuth, no bot identity).
Docs indexes count UTF-16 code units, not Python characters (see utf16_len).
Credentials: lib/google_oauth.py (token in ~/.config/agent-skeleton/google/gdocs-token.json).
Python 3.9+, standard library only.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
import google_oauth as go  # noqa: E402

TOOL = "gdocs"
DOCS_API = "https://docs.googleapis.com/v1"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DOC_MIME = "application/vnd.google-apps.document"
WRITE_SCOPE = "https://www.googleapis.com/auth/documents"
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]
EXPORT_MIME = {
    "md": "text/markdown", "txt": "text/plain", "html": "text/html", "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text", "rtf": "application/rtf",
    "epub": "application/epub+zip",
}
DOC_ID_RE = re.compile(r"/document/d/([a-zA-Z0-9_-]+)")


def raw(base, path, method="GET", params=None, body=None, want_bytes=False):
    return go.request(method, "%s/%s" % (base, path.lstrip("/")), go.access_token(TOOL),
                      params=params, body=body, want_bytes=want_bytes)


def docs_api(path, **kw):
    return go.check(*raw(DOCS_API, path, **kw))


def drive_api(path, **kw):
    return go.check(*raw(DRIVE_API, path, **kw))


def doc_id(handle):
    """A bare document id, or the id inside any Google Docs URL."""
    match = DOC_ID_RE.search(handle)
    if match:
        return match.group(1)
    if handle.startswith("http"):
        raise go.OAuthError("no document id in %s" % handle)
    return handle


def drive_quote(value):
    """A literal for a Drive `q` expression: backslash and single quote escaped."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def utf16_len(text):
    """Length in UTF-16 code units: what Docs indexes count (an emoji is 2)."""
    return len(text.encode("utf-16-le")) // 2


def _para_text(para):
    out = []
    for el in para.get("elements", []):
        run = el.get("textRun")
        if run:
            out.append(run.get("content", ""))
        elif "personProperties" in el.get("person", {}):
            out.append(el["person"]["personProperties"].get("name", ""))
        elif el.get("richLink"):
            out.append(el["richLink"].get("richLinkProperties", {}).get("title", ""))
    return "".join(out)


def doc_text(document):
    """Flatten a Docs document to plain text, tables included."""
    lines = []

    def walk(elements):
        for el in elements:
            if "paragraph" in el:
                lines.append(_para_text(el["paragraph"]).rstrip("\n"))
            elif "table" in el:
                for row in el["table"].get("tableRows", []):
                    cells = []
                    for cell in row.get("tableCells", []):
                        parts = [_para_text(c["paragraph"]).strip()
                                 for c in cell.get("content", []) if "paragraph" in c]
                        cells.append(" ".join(p for p in parts if p))
                    lines.append(" | ".join(cells))
            elif "tableOfContents" in el:
                walk(el["tableOfContents"].get("content", []))

    walk(document.get("body", {}).get("content", []))
    return "\n".join(lines)


def end_index(document):
    """Last insertable index: the body ends with a newline nothing can follow."""
    content = document.get("body", {}).get("content", [])
    return content[-1].get("endIndex", 2) - 1 if content else 1


def read_text_arg(args):
    if getattr(args, "text_file", None):
        with open(args.text_file, encoding="utf-8") as fh:
            return fh.read()
    return getattr(args, "text", None) or ""


# ---------------------------------------------------------------------------- commands
def cmd_login(args):
    return go.run_login(TOOL, SCOPES, args, must_have=[WRITE_SCOPE])


def cmd_logout(args):
    print("logged out" if go.logout(TOOL, revoke=not args.keep_grant) else "not logged in")


def cmd_search(args):
    clauses = ["trashed = false"]
    if not args.all_types:
        clauses.append("mimeType = %s" % drive_quote(DOC_MIME))
    if args.name:
        clauses.append("name contains %s" % drive_quote(args.name))
    if args.content:
        clauses.append("fullText contains %s" % drive_quote(args.content))
    if args.owner:
        clauses.append("%s in owners" % drive_quote(args.owner))
    if args.shared_with_me:
        clauses.append("sharedWithMe = true")
    params = {"q": " and ".join(clauses), "pageSize": min(args.limit, 100),
              "orderBy": args.order_by, "supportsAllDrives": "true",
              "includeItemsFromAllDrives": "true",
              "fields": "files(id,name,mimeType,owners(emailAddress),modifiedTime,webViewLink)"}
    files = drive_api("files", params=params).get("files", [])[:args.limit]
    if go.emit(files, args.json):
        return
    print("%d files" % len(files))
    for f in files:
        owner = (f.get("owners") or [{}])[0].get("emailAddress", "?")
        print("  %s  %-46s  %-32s  %s" % ((f.get("modifiedTime") or "")[:10], f["id"], owner,
                                          f.get("name")))


def cmd_info(args):
    params = {"fields": "id,name,mimeType,owners(emailAddress,displayName),createdTime,"
                        "modifiedTime,lastModifyingUser(emailAddress),webViewLink,"
                        "capabilities(canEdit,canComment,canShare),trashed",
              "supportsAllDrives": "true"}
    meta = drive_api("files/%s" % doc_id(args.doc), params=params)
    if go.emit(meta, args.json):
        return
    owner = (meta.get("owners") or [{}])[0]
    print("name      %s\nid        %s\nowner     %s <%s>\nmodified  %s by %s\ncanEdit   %s\nurl       %s"
          % (meta.get("name"), meta.get("id"), owner.get("displayName"), owner.get("emailAddress"),
             meta.get("modifiedTime"), (meta.get("lastModifyingUser") or {}).get("emailAddress", "?"),
             (meta.get("capabilities") or {}).get("canEdit"), meta.get("webViewLink")))


def cmd_get(args):
    document = docs_api("documents/%s" % doc_id(args.doc))
    if args.json or args.raw:
        go.emit(document, True)
        return
    print("# %s\n" % document.get("title"))
    print(doc_text(document))


def cmd_export(args):
    data = go.check(*raw(DRIVE_API, "files/%s/export" % doc_id(args.doc),
                         params={"mimeType": EXPORT_MIME[args.format]}, want_bytes=True))
    if args.format == "txt" and data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]                                       # Drive prepends a BOM
    if args.out:
        with open(args.out, "wb") as fh:
            fh.write(data)
        print("wrote %d bytes to %s" % (len(data), args.out))
    else:
        sys.stdout.buffer.write(data)


def cmd_create(args):
    document = docs_api("documents", method="POST", body={"title": args.title})
    did = document["documentId"]
    text = read_text_arg(args)
    if text:
        docs_api("documents/%s:batchUpdate" % did, method="POST", body={
            "requests": [{"insertText": {"location": {"index": 1}, "text": text}}]})
    url = "https://docs.google.com/document/d/%s/edit" % did
    if not go.emit({"documentId": did, "title": args.title, "url": url}, args.json):
        print("created: %s\nurl: %s" % (did, url))


def cmd_append(args):
    did = doc_id(args.doc)
    text = read_text_arg(args)
    if not text:
        raise go.OAuthError("need --text or --text-file")
    if not args.no_newline and not text.startswith("\n"):
        text = "\n" + text                                    # a new paragraph, not a run-on
    idx = end_index(docs_api("documents/%s" % did, params={"fields": "body.content"}))
    res = docs_api("documents/%s:batchUpdate" % did, method="POST", body={
        "requests": [{"insertText": {"location": {"index": idx}, "text": text}}]})
    if not go.emit(res, args.json):
        print("appended %d characters at index %d" % (utf16_len(text), idx))


def cmd_insert(args):
    res = docs_api("documents/%s:batchUpdate" % doc_id(args.doc), method="POST", body={
        "requests": [{"insertText": {"location": {"index": args.index}, "text": args.text}}]})
    if not go.emit(res, args.json):
        print("inserted %d UTF-16 units at index %d" % (utf16_len(args.text), args.index))


def cmd_replace(args):
    res = docs_api("documents/%s:batchUpdate" % doc_id(args.doc), method="POST", body={
        "requests": [{"replaceAllText": {
            "containsText": {"text": args.find, "matchCase": not args.ignore_case},
            "replaceText": args.replace}}]})
    if go.emit(res, args.json):
        return
    n = res.get("replies", [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    print("replaced %d occurrence(s)" % n)


def cmd_batch_update(args):
    with open(args.requests_file, encoding="utf-8") as fh:
        requests = json.load(fh)
    if isinstance(requests, dict):
        requests = requests.get("requests", [])
    go.emit(docs_api("documents/%s:batchUpdate" % doc_id(args.doc), method="POST",
                     body={"requests": requests}), True)


def cmd_probe_write(args):
    """Prove write access without changing anything: an empty replaceAllText search fails
    validation (400) only after the permission check, and matches nothing by definition.
    Docs, unlike Chat, separates 403 (denied) from 404 (no such document)."""
    did = doc_id(args.doc)
    status, payload = raw(DOCS_API, "documents/%s:batchUpdate" % did, method="POST", body={
        "requests": [{"replaceAllText": {"containsText": {"text": "", "matchCase": True},
                                         "replaceText": "probe"}}]})
    err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
    verdict = {400: "WRITE OK: rejected at validation, so authorization passed",
               403: "WRITE DENIED: the permission check failed",
               404: "NOT FOUND: the document does not exist or is not visible to you"}.get(
        status, "UNEXPECTED: see status and message")
    out = {"documentId": did, "httpCode": status, "status": err.get("status", ""),
           "message": err.get("message", ""), "verdict": verdict}
    if not go.emit(out, args.json):
        print("HTTP %s %s\n%s" % (status, out["status"], verdict))


def cmd_scopes(args):
    info = go.tokeninfo(go.access_token(TOOL))
    granted = sorted(info.get("scope", "").split())
    if not go.emit({"expires_in": info.get("expires_in"), "scopes": granted}, args.json):
        for s in granted:
            print("  [%s] %s" % ("W" if s in SCOPES else " ", s))


def cmd_token(_args):
    print(go.access_token(TOOL))


def build_parser():
    p = argparse.ArgumentParser(prog="gdocs.py", description="Google Docs as yourself.")
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
    sp = add("search", cmd_search, "find documents in Drive")
    sp.add_argument("--name", help="substring of the file name")
    sp.add_argument("--content", help="full-text search inside documents")
    sp.add_argument("--owner", help="owner email address")
    sp.add_argument("--shared-with-me", action="store_true")
    sp.add_argument("--all-types", action="store_true", help="not only Google Docs")
    sp.add_argument("--order-by", default="modifiedTime desc")
    sp.add_argument("--limit", type=int, default=20)
    add("info", cmd_info, "Drive metadata").add_argument("doc")
    sp = add("get", cmd_get, "read a document as plain text")
    sp.add_argument("doc")
    sp.add_argument("--raw", action="store_true", help="full Docs JSON with structure")
    sp = add("export", cmd_export, "export through Drive", False)
    sp.add_argument("doc")
    sp.add_argument("--format", choices=sorted(EXPORT_MIME), default="md")
    sp.add_argument("--out", help="write to this file instead of stdout")
    sp = add("create", cmd_create, "create a new document")
    sp.add_argument("--title", required=True)
    sp.add_argument("--text")
    sp.add_argument("--text-file")
    sp = add("append", cmd_append, "append text at the end")
    sp.add_argument("doc")
    sp.add_argument("--text")
    sp.add_argument("--text-file")
    sp.add_argument("--no-newline", action="store_true", help="continue the last paragraph")
    sp = add("insert", cmd_insert, "insert text at a UTF-16 index")
    sp.add_argument("doc")
    sp.add_argument("--index", type=int, required=True)
    sp.add_argument("--text", required=True)
    sp = add("replace", cmd_replace, "replace every occurrence of a string")
    sp.add_argument("doc")
    sp.add_argument("--find", required=True)
    sp.add_argument("--replace", required=True)
    sp.add_argument("--ignore-case", action="store_true")
    sp = add("batch-update", cmd_batch_update, "POST a batchUpdate request list (JSON file)", False)
    sp.add_argument("doc")
    sp.add_argument("requests_file")
    add("probe-write", cmd_probe_write, "prove write access, change nothing").add_argument("doc")
    add("scopes", cmd_scopes, "what the stored token can do")
    add("token", cmd_token, "print a fresh bearer token", False)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    go.main_guard(main)
