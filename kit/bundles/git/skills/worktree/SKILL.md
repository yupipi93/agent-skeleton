---
name: worktree
description: "Slash command: run one or more tasks (ticket keys or free text, separated by |) in isolated worktrees: lease, branch, do the work, open the PR, return the slot."
disable-model-invocation: true
---

# /worktree

Run the task(s) given after the command, each in its own worktree. Load skill
`git-worktrees` first and follow it: it holds the safety rules this command relies on.

```text
/worktree PROJ-410
/worktree PROJ-410 | PROJ-411
/worktree add a lifecycle rule to the logs bucket in platform-iac
```

## Steps

1. **Split** the arguments on `|` (or an explicit "in parallel"). Each task is a ticket
   key or a description.
2. **Resolve the repository** under `projects/` for each task (from the text or the
   ticket). Ambiguous: ask once.
3. **Read tickets.** For each key, `kit/bundles/jira/scripts/jira-forms.sh <KEY>` (best
   effort) and `kit/bundles/jira/scripts/jira-issue.sh <KEY>` when the jira bundle is on.
4. **Check separability** (several tasks). Overlapping files: say so and run them one
   after the other in a single worktree.
5. **Lease one worktree per task** with the branch in the same call:
   `treehouse get --lease --json --lease-holder <KEY-or-slug> -b <type>/<desc>-<KEY>`
   (or the `git worktree add` fallback). Record each path and lease id; report the paths.
6. **Execute.** One task: do it here. Several: one background worker per worktree, each
   brief carrying the absolute path ("work only inside it"), its branch, its file scope,
   the finish sequence and "do not return the worktree".
7. **Land each task**: validate, commit (skill `git-conventional-commits`), push, open the
   PR with a full body (skill `git-branch-pr-workflow`). No `terraform apply` without an
   explicit yes, and never two applies on one state at once.
8. **Return** each slot after its push:
   `treehouse return --force --if-lease-id "$LEASE_ID" "$WT"` (or `git worktree remove`).
9. **Report** per task: branch, PR URL, worktree returned or still leased and why.

## Result line

End with exactly one of:

- `✅ N task(s) landed: <branch -> PR url, ...>; worktrees returned.`
- `⚠️ <task> landed, <task> paused (<reason>; next: <step>); its worktree is still leased.`
- `⚠️ Tasks overlap on <files>: ran sequentially in one worktree.`
- `❌ Worktree run failed at <step>: <path> left leased for inspection.`
