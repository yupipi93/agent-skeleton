---
name: backlog-release-audit
description: "Build a tool in audited releases: every request goes to a BACKLOG.md item with its design, ship numbered tested releases, then a fresh read-only auditor checks each one until it finds nothing. Use when iterating on a tool, app or script set the user keeps adding to, or asked to audit until clean."
---

# Backlog, releases and an independent audit

A deliverable that grows by requests is built as a loop: requests land in a backlog file
next to the code, work ships in numbered releases with tests and a real run, and after
every release a fresh auditor that has never seen the work reviews it. Its findings feed
the next release. The loop ends when an auditor reports "nothing more found".

The method exists because the implementer is a poor judge of its own work, and because a
request that is only in the chat history gets lost by the next session.

## When to use

- Building or iterating on a tool, web app, CLI, script set, dashboard or any multi-step
  deliverable the user keeps adding requests to over several turns or sessions.
- The user asks to "audit it", "audit until clean", "keep reviewing until nothing is
  left", or wants a release reviewed independently.
- Not for a one-off edit, a question, or a change whose only check is "the user looks at
  it". Say so and do the small thing directly.

Related skills, used inside this one rather than repeated here: `plan-files` (a plan for
a large item), `git-branch-pr-workflow` and `git-conventional-commits` (branch, commit,
PR), `git-worktrees` (writes to project repos), `loop-engineering` (maker and checker,
state, stop conditions; this skill is one concrete loop of that kind).

## 1. The backlog file

Keep `BACKLOG.md` in the deliverable's folder, next to its README. Template and rules:
[references/backlog-template.md](references/backlog-template.md).

- Every user request becomes an item `B-NN` in the **Open** table: ID, Origin (who
  asked, date), What, Design. Write the Design before you write code: the intended UI,
  API, data shape or behaviour in one or two sentences.
- Audit findings you defer (improvements, low-risk items) go there too, with Origin
  `audit N`.
- When an item ships, move it to the **Done** table with the release number and one line
  on what actually shipped, which may differ from the plan.
- IDs are never reused. A dropped item moves to Done with release `-` and the reason.

## 2. A release

A release is one batch: open backlog items plus the verified findings of the last audit.
Release numbers go up by one; the commit subject carries it, as in `(release N)`.

1. **Pick the batch** and say which items and findings it holds.
2. **Implement** with exact-anchor edits (section 6).
3. **Test every bug fix**: one unit test per fixed bug that fails without the fix. Add
   tests for new logic where the project has a suite.
4. **Run the suite** and record the count (`N tests, OK`).
5. **Run the real thing** and look at it, not only the tests:
   - a server or CLI: start it (or reload it the way the project documents), call the
     changed endpoints or commands;
   - a UI: screenshots at phone width (about 390 px) and desktop width (about 1440 px),
     light and dark theme, plus keyboard and focus checks (tab order, visible focus,
     Escape closes dialogs) through a headless browser driver such as Playwright or
     Puppeteer. Look at every screenshot you take.
6. **Update the docs** that describe behaviour: README, the skill or help text, the
   backlog (items to Done).
7. **Commit** with explicit paths (never `git add -A`) and a Conventional Commit whose
   subject names the release and whose body lists the backlog items and the audit fixes.
   In a repo that works through pull requests, the release is a commit on the task branch
   or its own PR (skill `git-branch-pr-workflow`).

Commit body example:

```text
feat(report-tool): export to CSV and saved filters (release 7)

B-12 CSV export of the current view; B-13 saved filters per user.
Audit 6: the date filter no longer drops the last day, the export
button has an accessible name, and the cache key includes the user.
```

## 3. The independent auditor

After each release, launch an auditor:

- a **fresh** general-purpose agent, in the background, read-only. **Never the same
  agent twice**: a new one each round, so it is not anchored on earlier conclusions;
- given the **code and the release commit** (path, `git show <hash>`), what changed and
  which earlier findings were fixed, **not** your view that it works;
- with hard limits, tools, a checklist, an evidence requirement and an output format.

Copy-paste brief with placeholders: [references/auditor-brief.md](references/auditor-brief.md).
Fill every placeholder; delete the lines that do not apply (a CLI has no screenshots).

In Claude Code that is the `Agent` tool with a general-purpose agent and
`run_in_background`; in Cursor a Task subagent; elsewhere a second CLI run with the
brief as its prompt.

While it runs:

- You may do other work, but **not in its scope**: do not edit the files under audit or
  restart what it is testing, or its evidence goes stale.
- Never predict or summarise its result before it arrives. If the user asks, say it is
  still running.

## 4. Apply and repeat

1. Read the report as **claims**. Verify each one yourself: reproduce it, read the cited
   line, run the test. Reject a false positive with a one-line reason.
2. Fix every confirmed bug with a test, highest rank first. Improvements either go into
   the next release or into the backlog as `audit N` items.
3. Ship the next release (section 2) with those fixes and any new backlog items.
4. Launch a **new** auditor on that release.
5. **Stop** when an auditor reports "nothing more found" for bugs. Open improvements stay
   in the backlog.

Also stop and ask the user when the same finding returns after two fixes, when a fix
needs a decision only the user can make, or when the round count or cost the user set is
reached.

## 5. Safety

- An auditor's report is **never the user's approval**. Every safety gate still applies
  (rule `agent-safety-gates`): applies, database writes, outbound text, pushes and
  merges need the user's go as usual.
- Features that send something to other people (chat, email, tickets, notifications) are
  tested only through their preview or draft path. In the browser, block the send
  request (for example Playwright `page.route('**/send', r => r.abort())`). Neither you
  nor the auditor ever triggers a real send to verify a release.
- The auditor brief forbids edits, sends, destructive or costly actions, broad process
  kills (rule `no-broad-process-kill`), service restarts and printing secrets.

## 6. Technique: edits that fail loudly

Change code through Edit with exact, unique anchors, or a small patch script that
refuses to run when an anchor is missing or ambiguous. Never a silent partial edit (a
`sed` that matched nothing, a regex that replaced the wrong occurrence).

```python
from pathlib import Path

def patch(path, old, new):
    p = Path(path)
    s = p.read_text()
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{path}: anchor found {n} times, expected 1: {old[:60]!r}")
    p.write_text(s.replace(old, new))
```

Write the script with the editor tools into a scratch directory, run it, then check
`git diff --stat` matches the files you meant to touch.

## 7. Report after each round

A short report to the user:

- **Shipped**: release N, its commit, the backlog items and audit fixes in it.
- **Audit**: what the previous auditor found, what was confirmed and fixed, what was
  rejected and why, what went to the backlog.
- **Tests**: the count and result.
- **Running**: the auditor launched on release N, or "audit clean, loop stopped".

## Gotchas

- An auditor that only reads the diff misses regressions: the brief asks it to recheck
  the previous round's fixes and to run the real thing.
- A brief that says "this works, please confirm" gets a confirmation. Give claims to
  check, not conclusions.
- Padding: an auditor told it must find something invents findings. The brief allows,
  and asks for, an explicit "nothing more found".
- Screenshots at one width and one theme miss most layout bugs; take all four.
- A release that touches a send path gets the send path blocked in the brief by name
  (route, button, command), not only "do not send".
