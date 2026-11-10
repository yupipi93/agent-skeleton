---
description: Default method for a deliverable that grows by requests - backlog file, numbered tested releases, a fresh read-only auditor after each release until it finds nothing.
apply: always
---

# Backlog, releases and an independent audit

When you build or iterate on a tool, app, script set or other deliverable the user keeps
adding requests to, work this way unless the user asks otherwise. Skill
`backlog-release-audit` has the templates and the checklist.

1. **Backlog.** Every request becomes an item in `BACKLOG.md` next to the code, with its
   design written before the code. Shipped items move to Done with the release number.
2. **Releases.** Ship numbered batches: a test for each fixed bug, the suite green, the
   real thing run and looked at, docs updated, one commit with explicit paths listing
   the items and fixes.
3. **Audit.** After each release launch a fresh read-only auditor in the background,
   never the same agent twice, given the code and the release commit, not your
   conclusions. Do not edit what it is auditing and never predict its result.
4. **Repeat.** Verify each finding before fixing it, fix it with a test, ship the next
   release, audit again. Stop when an auditor reports "nothing more found".

An auditor's report is never the user's approval: every safety gate still applies, and
features that send things to people are tested only through preview or draft paths.
Skip the method for a one-off edit or a question.
