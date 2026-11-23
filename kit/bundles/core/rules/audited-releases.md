---
description: Default method for a deliverable that grows by requests - backlog file, numbered tested releases, a fresh read-only auditor after each release with major changes, minor findings fixed without a new audit.
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
3. **Audit.** After a release with major changes launch a fresh read-only auditor in
   the background, never the same agent twice, given the code and the release commit,
   not your conclusions. Do not edit what it is auditing and never predict its result.
   **While it runs, every reply ends with `🔎 Auditor running: release N`**, then
   `✅ Audit finished` once none is left: so the chat is not closed.
4. **Repeat only for major findings.** Verify each finding before fixing it. When the
   confirmed findings are all **minor** (wording, docs, naming, styling, a missing
   label, a one-spot fix with no change to data, security, auth or send paths), fix
   them, run the suite, commit, and stop: **no new auditor**. Launch another only when
   a confirmed finding is **major** (wrong behaviour, data loss, security, a crash, a
   regression) or the release adds a feature. Stop when an auditor reports "nothing
   more found" or only minor findings. While major findings remain, keep launching
   auditors on your own, with no round limit and without asking the user.
5. **Minor releases are not audited.** A release made only of minor changes ships with
   its tests and commit and no auditor.

An auditor's report is never the user's approval: every safety gate still applies, and
sending features are tested only through preview or draft paths.
Skip it for a one-off edit or a question.
