#!/usr/bin/env python3
"""jira-comment.py: write rich Jira comments and descriptions from Markdown (ADF).

Usage:
  kit/bundles/jira/scripts/jira-comment.py PROJ-123 --comment "Ready to test."
  kit/bundles/jira/scripts/jira-comment.py PROJ-123 --comment-file note.md
  kit/bundles/jira/scripts/jira-comment.py PROJ-123 --update-comment 10042 --comment-file note.md
  kit/bundles/jira/scripts/jira-comment.py PROJ-123 --description-file desc.md [--summary "New title"]
  kit/bundles/jira/scripts/jira-comment.py PROJ-123 --comment-file note.md --dry-run

Markdown subset: headings, GFM tables, bullet and numbered lists, fenced code, panels
("> [!warning]"), **bold**, `code`, [links](https://...), [[PROJ-123]] issue cards,
@[Name](accountId) mentions, emojis. See kit/bundles/jira/scripts/lib/adf.py.

Safety: the text goes through the shared secret patterns
(kit/bundles/core/scripts/lib/secret-patterns.txt) and is refused on a match. That is a
backstop: the outbound-text-safety rule (review, exact text shown, approval) comes first.

Config: ~/.config/agent-skeleton/atlassian.env (JIRA_SITE, JIRA_EMAIL, JIRA_API_TOKEN),
each overridable by an environment variable; ATLASSIAN_ENV_FILE points elsewhere.
Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error, 5 blocked by the text guard.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "core", "scripts", "lib"))
import adf  # noqa: E402
import envfile  # noqa: E402
import secretscan  # noqa: E402

CONFIG = os.environ.get("ATLASSIAN_ENV_FILE") or os.path.expanduser("~/.config/agent-skeleton/atlassian.env")
TIMEOUT = int(os.environ.get("JIRA_HTTP_TIMEOUT") or 30)


def conf(key, default=""):
    value = envfile.get(CONFIG, key, None)
    return value if value not in (None, "") else default


def site():
    s = conf("JIRA_SITE").replace("https://", "").replace("http://", "").split("/")[0]
    if not s:
        sys.stderr.write("error: JIRA_SITE is not set (for example your-org.atlassian.net).\n"
                         "Run 'bin/skeleton setup jira', or export JIRA_SITE=your-org.atlassian.net\n")
        sys.exit(3)
    return s


def issue_url(host, key):
    if conf("JIRA_LINK_STYLE", "browse") == "portal" and conf("JIRA_PORTAL_ID"):
        return "https://%s/servicedesk/customer/portal/%s/%s" % (host, conf("JIRA_PORTAL_ID"), key)
    return "https://%s/browse/%s" % (host, key)


def call(host, path, method, payload):
    email, token = conf("JIRA_EMAIL"), conf("JIRA_API_TOKEN")
    if not email or not token:
        sys.stderr.write("error: missing JIRA_EMAIL or JIRA_API_TOKEN in %s (or the environment).\n"
                         "Run 'bin/skeleton setup jira'.\n" % CONFIG)
        sys.exit(3)
    if os.path.exists(CONFIG):
        ok, mode = envfile.check_mode(CONFIG)
        if not ok:
            sys.stderr.write("warning: %s is mode %s; run chmod 600 %s\n" % (CONFIG, mode, CONFIG))
    auth = base64.b64encode(("%s:%s" % (email, token)).encode()).decode()
    req = urllib.request.Request(
        "https://%s%s" % (host, path), data=json.dumps(payload).encode(), method=method,
        headers={"Authorization": "Basic " + auth, "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, "unreachable: %s" % e


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="jira-comment.py", description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("issue", help="issue key, e.g. PROJ-123")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--comment", help="comment text (Markdown)")
    src.add_argument("--comment-file", help="comment from a Markdown file ('-' for stdin)")
    src.add_argument("--description-file", help="replace the description with this Markdown file")
    ap.add_argument("--summary", help="new summary (with --description-file)")
    ap.add_argument("--update-comment", metavar="COMMENT_ID", help="edit this comment instead of adding one")
    ap.add_argument("--em-dash", action="store_true", help="also block U+2014 (house style)")
    ap.add_argument("--dry-run", action="store_true", help="print the request and ADF, send nothing")
    args = ap.parse_args(argv)

    if args.summary and not args.description_file:
        ap.error("--summary only goes with --description-file")
    if args.update_comment and args.description_file:
        ap.error("--update-comment edits a comment; it cannot be combined with --description-file")
    try:
        if args.comment is not None:
            text = args.comment
        else:
            path = args.comment_file or args.description_file
            text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    except OSError as e:
        sys.stderr.write("error: %s\n" % e)
        return 2
    if not text.strip():
        sys.stderr.write("error: the text is empty\n")
        return 2

    try:
        hit = secretscan.scan("\n".join(filter(None, [args.summary or "", text])), em_dash=args.em_dash)
    except OSError:
        hit = "pattern file unreadable"
    if hit:
        sys.stderr.write("BLOCKED (%s): nothing was sent. Reference secrets by name, never by value.\n" % hit)
        return 5

    host = site()
    doc = adf.md_to_adf(text, host)
    if args.description_file:
        fields = {"description": doc}
        if args.summary:
            fields["summary"] = args.summary
        method, path, payload, ok_codes = "PUT", "/rest/api/3/issue/%s" % args.issue, {"fields": fields}, (204,)
    elif args.update_comment:
        method, path, payload, ok_codes = ("PUT", "/rest/api/3/issue/%s/comment/%s" % (args.issue, args.update_comment),
                                           {"body": doc}, (200,))
    else:
        method, path, payload, ok_codes = "POST", "/rest/api/3/issue/%s/comment" % args.issue, {"body": doc}, (200, 201)

    if args.dry_run:
        print("dry-run: %s https://%s%s" % (method, host, path))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    status, body = call(host, path, method, payload)
    if status not in ok_codes:
        sys.stderr.write("error: HTTP %s: %s\n" % (status, body[:500]))
        return 4
    try:
        comment_id = json.loads(body).get("id", "") if body else ""
    except (ValueError, AttributeError):
        comment_id = ""
    print("ok: %s%s" % (issue_url(host, args.issue), (" comment_id=%s" % comment_id) if comment_id else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
