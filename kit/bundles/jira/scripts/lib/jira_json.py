#!/usr/bin/env python3
"""JSON plumbing for the jira bundle's shell scripts (render, resolve, build payloads).

The shell scripts fetch with curl and hand the response files to this module, so every
renderer can be tested offline with fixtures. Subcommands:

  field FILE PATH [DEFAULT]          print a dotted path ("fields.status.name", "0.id")
  error FILE                         one-line summary of a Jira error response
  issue ISSUE_FILE [COMMENT_FILE...] --mode full|meta|comments [--url-site S]
                                     render an issue (env: JIRA_SITE, JIRA_LINK_STYLE,
                                     JIRA_PORTAL_ID, JIRA_REQUEST_TYPE_FIELD, COMMENT_TOTAL)
  merge-comments COMMENT_FILE...     print {"comments": [...]} with every page joined
  search FILE                        render a JQL result as a Markdown table
  transitions FILE                   list transitions (id, name, target, category)
  resolve TARGET FILE                print "<id>\\t<name>\\t<status>" for TARGET; exit 4 ambiguous,
                                     exit 1 not found
  hop FILE                           first transition into an in-progress status
  forms FILE KEY                     render ProForma forms (list of full form objects)
  create-payload                     build the create body from env (see jira-create.sh)
  issue-url KEY                      the link for KEY per JIRA_LINK_STYLE

Python 3.8+ compatible, stdlib only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adf import adf_to_markdown, md_to_adf  # noqa: E402

# Never treat these as "Done": a cancellation lands in the done category too.
ABANDONED = ("cancel", "reject", "decline", "won't do", "wont do", "duplicate", "abandon")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def issue_url(key, site=None, style=None, portal=None):
    site = site or os.environ.get("JIRA_SITE", "")
    style = (style or os.environ.get("JIRA_LINK_STYLE") or "browse").strip().lower()
    portal = portal or os.environ.get("JIRA_PORTAL_ID", "")
    if style == "portal" and portal:
        return "https://%s/servicedesk/customer/portal/%s/%s" % (site, portal, key)
    return "https://%s/browse/%s" % (site, key)


def field(data, path, default=None):
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return default
        elif isinstance(cur, dict):
            if part not in cur:
                return default
            cur = cur[part]
        else:
            return default
    return cur


def error_summary(data):
    if not isinstance(data, dict):
        return str(data)[:300]
    parts = list(data.get("errorMessages") or [])
    errors = data.get("errors") or {}
    if isinstance(errors, list):
        # Forms API shape: [{"status": 404, "code": "...", "title": "...", "detail": "..."}]
        for e in errors:
            if isinstance(e, dict):
                parts.append(" ".join(str(e[k]) for k in ("code", "detail") if e.get(k)))
            else:
                parts.append(str(e))
    else:
        for k, v in errors.items():
            parts.append("%s: %s" % (k, v))
    if data.get("message"):
        parts.append(str(data["message"]))
    return "; ".join(parts)[:500] or json.dumps(data)[:300]


def _person(value, empty="unassigned"):
    return (value or {}).get("displayName") or empty


def _request_type(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return (value.get("requestType") or {}).get("name") or "?"
    return "-"


def merge_comments(paths):
    out = []
    for p in paths:
        out.extend(_load(p).get("comments", []))
    return {"comments": out}


def render_issue(issue, comments, mode="full", comment_total=None):
    f = issue.get("fields", {})
    rt_field = os.environ.get("JIRA_REQUEST_TYPE_FIELD") or "customfield_10010"
    lines = []
    if mode in ("full", "meta"):
        lines += ["# %s  %s" % (issue.get("key"), f.get("summary", "")), "",
                  "| Field | Value |", "|---|---|",
                  "| Status | %s |" % field(f, "status.name", "?"),
                  "| Type | %s |" % field(f, "issuetype.name", "?")]
        if f.get(rt_field) is not None:
            lines.append("| Request type | %s |" % _request_type(f.get(rt_field)))
        lines += ["| Priority | %s |" % (field(f, "priority.name") or "-"),
                  "| Assignee | %s |" % _person(f.get("assignee")),
                  "| Reporter | %s |" % _person(f.get("reporter"), "-"),
                  "| Labels | %s |" % (", ".join(f.get("labels") or []) or "-"),
                  "| Created | %s |" % str(f.get("created", "?"))[:19],
                  "| Updated | %s |" % str(f.get("updated", "?"))[:19],
                  "| Comments | %s |" % (comment_total if comment_total not in (None, "") else len(comments)),
                  "| URL | %s |" % issue_url(issue.get("key")), ""]
    if mode == "meta":
        return "\n".join(lines)
    if mode == "full":
        body = adf_to_markdown(f.get("description")).strip()
        lines += ["## Description", "",
                  body or "_(empty: on a service desk the detail may be in the Attached forms, "
                          "read them with kit/bundles/jira/scripts/jira-forms.sh)_", ""]
        attachments = f.get("attachment") or []
        lines += ["## Attachments (%d)" % len(attachments), ""]
        if not attachments:
            lines.append("_(none)_")
        for a in sorted(attachments, key=lambda x: x.get("created", "")):
            lines.append("- %s (%s, %d KB, by %s, %s), id %s" % (
                a.get("filename", "?"), a.get("mimeType", "?"), max(1, int(a.get("size", 0)) // 1024),
                _person(a.get("author"), "?"), str(a.get("created", "?"))[:19], a.get("id")))
        lines.append("")
    lines.append("## Comments (%d, oldest first)" % len(comments))
    if not comments:
        lines += ["", "_(none)_"]
    for c in comments:
        lines += ["", "### %s, %s (id %s)" % (_person(c.get("author"), "?"),
                                             str(c.get("created", "?"))[:19], c.get("id")),
                  "", adf_to_markdown(c.get("body")).strip()]
    return "\n".join(lines)


def render_search(data):
    issues = data.get("issues", [])
    if not issues:
        return "no issues match"
    lines = ["| Key | Status | Summary | Assignee | Updated |", "|---|---|---|---|---|"]
    for issue in issues:
        f = issue.get("fields", {})
        lines.append("| [%s](%s) | %s | %s | %s | %s |" % (
            issue.get("key"), issue_url(issue.get("key")), field(f, "status.name", "?"),
            str(f.get("summary", "")).replace("|", "\\|"), _person(f.get("assignee"), "-"),
            str(f.get("updated", "?"))[:10]))
    more = "" if data.get("isLast", True) else " (more available, raise --max)"
    lines += ["", "%d shown%s" % (len(issues), more)]
    return "\n".join(lines)


def render_transitions(data):
    return "\n".join("  %-5s %-32s -> %s (%s)" % (
        t.get("id"), t.get("name"), field(t, "to.name", "?"), field(t, "to.statusCategory.key", "?"))
        for t in data.get("transitions", []))


def _abandoned(t):
    text = (str(t.get("name", "")) + " " + str(field(t, "to.name", ""))).lower()
    return any(w in text for w in ABANDONED)


def resolve(target, data):
    """Return (transition, error). error is None, 'ambiguous' or 'not-found'."""
    want = target.strip().lower()
    transitions = data.get("transitions", [])
    for t in transitions:  # 1. exact target status
        if str(field(t, "to.name", "")).strip().lower() == want:
            return t, None
    for t in transitions:  # 2. exact transition name ("Start")
        if str(t.get("name", "")).strip().lower() == want:
            return t, None
    if want in ("done", "closed", "resolved"):  # 3. done category, minus cancellations
        cands = [t for t in transitions
                 if field(t, "to.statusCategory.key") == "done" and not _abandoned(t)]
        if len(cands) == 1:
            return cands[0], None
        if len(cands) > 1:
            return cands, "ambiguous"
    wants_abandon = any(w in want for w in ABANDONED)
    for t in transitions:  # 4. substring, still never a cancellation unless named
        if want and want in str(field(t, "to.name", "")).strip().lower():
            if _abandoned(t) and not wants_abandon:
                continue
            return t, None
    return None, "not-found"


def hop(data):
    for t in data.get("transitions", []):
        if field(t, "to.statusCategory.key") == "indeterminate" and not _abandoned(t):
            return t
    return None


def _tsv(t):
    return "%s\t%s\t%s" % (t.get("id"), t.get("name"), field(t, "to.name", "?"))


def _forms_answer(q, answers):
    a = answers.get(q["key"])
    if not a:
        return None
    if str(a.get("text", "") or "").strip():
        return str(a["text"])
    if a.get("adf"):
        text = adf_to_markdown(a["adf"]).strip()
        return text.replace("\n", "\n  ") or None
    if a.get("choices"):
        labels = {c.get("id"): c.get("label") for c in field(q, "value.choices", []) or []}
        return ", ".join(str(labels.get(c, c)) for c in a["choices"])
    if a.get("date"):
        return a["date"] + ((" " + a["time"]) if a.get("time") else "")
    if a.get("users"):
        return ", ".join(u.get("name") or u.get("displayName") or u.get("id", "")
                         if isinstance(u, dict) else str(u) for u in a["users"])
    if a.get("files"):
        return ", ".join(x.get("name", "?") if isinstance(x, dict) else str(x) for x in a["files"])
    return None


def render_forms(forms, key):
    lines = ["## Attached forms: %s" % key]
    for form in forms:
        name = field(form, "design.settings.name") or field(form, "formTemplate.name") or form.get("id", "form")
        lines += ["", "### %s" % name]
        answers = field(form, "state.answers", {}) or {}
        questions = field(form, "design.questions", {}) or {}

        def order(item):
            pos = item[1].get("position")
            if isinstance(pos, int):
                return pos
            try:
                return int(item[0])
            except ValueError:
                return 0
        for qkey, q in sorted(questions.items(), key=order):
            val = _forms_answer({"key": qkey, "value": q}, answers)
            if val is None:
                continue
            label = str(q.get("label") or q.get("questionKey") or qkey).rstrip().rstrip(":")
            lines.append("- **%s**: %s" % (label, val))
    return "\n".join(lines)


def create_payload(env):
    """Build the POST /rest/api/3/issue body from environment variables."""
    desc_text = env.get("DESCRIPTION", "")
    if env.get("DESCRIPTION_FILE"):
        with open(env["DESCRIPTION_FILE"], encoding="utf-8") as f:
            desc_text = f.read()
    fields = {
        "project": {"key": env["PROJECT"]},
        "issuetype": {"name": env["ISSUETYPE"]},
        "summary": env["SUMMARY"],
        "description": md_to_adf(desc_text, env.get("JIRA_SITE")),
    }
    if env.get("ASSIGNEE"):
        fields["assignee"] = {"accountId": env["ASSIGNEE"]}
    if env.get("REPORTER"):
        fields["reporter"] = {"accountId": env["REPORTER"]}
    if env.get("REQUEST_TYPE"):
        fields[env.get("JIRA_REQUEST_TYPE_FIELD") or "customfield_10010"] = env["REQUEST_TYPE"]
    if env.get("PRIORITY"):
        fields["priority"] = {"name": env["PRIORITY"]}
    if env.get("PARENT"):
        fields["parent"] = {"key": env["PARENT"]}
    labels = [x for x in env.get("LABELS", "").split("\n") if x.strip()]
    if labels:
        fields["labels"] = labels
    return {"fields": fields}


def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(__doc__ + "\n")
        return 0 if argv else 64
    cmd, args = argv[0], argv[1:]
    if cmd == "field":
        val = field(_load(args[0]), args[1], args[2] if len(args) > 2 else None)
        if val is None:
            return 1
        print(json.dumps(val) if isinstance(val, (dict, list)) else val)
        return 0
    if cmd == "error":
        try:
            print(error_summary(_load(args[0])))
        except (OSError, ValueError):
            try:
                print(open(args[0], encoding="utf-8", errors="replace").read()[:300].strip())
            except OSError:
                print("(no response body)")
        return 0
    if cmd == "issue":
        mode = "full"
        if "--mode" in args:
            i = args.index("--mode")
            mode = args[i + 1]
            args = args[:i] + args[i + 2:]
        comments = merge_comments(args[1:])["comments"]
        print(render_issue(_load(args[0]), comments, mode, os.environ.get("COMMENT_TOTAL")))
        return 0
    if cmd == "merge-comments":
        print(json.dumps(merge_comments(args), ensure_ascii=False))
        return 0
    if cmd == "search":
        print(render_search(_load(args[0])))
        return 0
    if cmd == "transitions":
        print(render_transitions(_load(args[0])))
        return 0
    if cmd == "resolve":
        t, err = resolve(args[0], _load(args[1]))
        if err == "ambiguous":
            sys.stderr.write("ambiguous: %d transitions land in a done status, name one:\n%s\n" % (
                len(t), "\n".join("  --to '%s'" % field(x, "to.name", "?") for x in t)))
            return 4
        if err:
            return 1
        print(_tsv(t))
        return 0
    if cmd == "hop":
        t = hop(_load(args[0]))
        if not t:
            return 1
        print(_tsv(t))
        return 0
    if cmd == "forms":
        data = _load(args[0])
        print(render_forms(data if isinstance(data, list) else [data], args[1]))
        return 0
    if cmd == "create-payload":
        print(json.dumps(create_payload(os.environ), ensure_ascii=False, indent=2))
        return 0
    if cmd == "issue-url":
        print(issue_url(args[0]))
        return 0
    sys.stderr.write("jira_json.py: unknown command %r\n" % cmd)
    return 64


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
