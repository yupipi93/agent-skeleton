---
name: devops-ticket-workflow
description: "End-to-end lifecycle for a DevOps or engineering ticket: read the ticket and its forms, pick the repo, branch in a worktree, change, plan, PR, client-safe comment, transition. Use when given a Jira key to resolve, or asked to create and then work a ticket."
---

# DevOps ticket workflow

The orchestrator for one ticket, in either direction:

- **Inbound**: the user gives a key (`PROJ-123`). Read it, do the work, close the loop.
- **Outbound**: the user describes work with no ticket. Create the ticket first (after
  approval), then do the work.

Companion skills: `jira-tickets` (scripts and text formats), `jira-board-config` (the
board's values), `git-branch-pr-workflow` and `git-worktrees` (branch, PR, isolation),
`git-conventional-commits`. Rules that always apply: `outbound-text-safety`,
`worktree-for-project-writes`, and `terraform-apply-requires-approval` when the
terraform bundle is on.

The order below is canonical; skip or merge steps when the situation calls for it (a
read-only investigation has no branch). The invariants never move: **text gate on every
write, branch before the first edit, PR after, no apply without an explicit yes**.

## 1. Read or create the ticket

**Inbound**

```bash
kit/bundles/jira/scripts/jira-forms.sh PROJ-123 || true   # forms: best effort
kit/bundles/jira/scripts/jira-issue.sh PROJ-123           # fields, description, every comment
```

Summarize the current request in a few lines, calling out what any comment changed, and
note open questions. If something is critically unclear, ask one question now.

**Outbound**: follow "Creating an issue" in `jira-tickets` (board choice, title format,
description template, assignee and reporter, proposal, approval, then
`jira-create.sh`). Return the URL.

## 2. Choose the repository

Map the ticket to a repository under `projects/` (component tag, service named, cloud
project, the board's `[routing]`). Link a missing one with `bin/skeleton projects add
<name>`. Ambiguous: ask. Several repos: one branch and one PR per repo.

## 3. Branch in a worktree

Follow `git-worktrees`: lease a worktree with the branch created in the same call,
named `<type>/<short-desc>-PROJ-123`. Every edit and command for this ticket runs in
that worktree, never in the shared checkout. One ticket per branch and per worktree.

## 4. Pick the ticket up

```bash
kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --to "In Progress"
```

Optionally add a one-line comment ("Picked this up.") through the gate.

## 5. Change and validate

Make the change, then validate what the repo supports: formatters and linters, tests,
`terraform validate` and `terraform plan` for infrastructure. Commit with Conventional
Commits, ticket key in the subject or a `Refs: PROJ-123` footer.

## 6. Plan, apply, manual steps

- Infrastructure: summarize the plan (adds, changes, destroys; call out replacements).
  **Never apply without an explicit yes.** Hand the user a copy-paste block instead:

  ```bash
  terraform workspace select <env> && terraform apply -target=<address>
  ```

  Prefer a targeted apply for a scoped change; never force-unlock a state.
- Manual steps (console, access grants, DNS): an ordered checklist, then confirm each.
- Two tickets on the same infrastructure repo share remote state: never two applies at
  once; give the order.

## 7. Open the PR

Push and open the PR as `git-branch-pr-workflow` describes: full body (Summary, Changes,
Validation, Rollback), ticket link, default reviewers plus the module owner when the
board or repo names one. The PR text passes the gate too. Return the PR URL.

## 8. Close the loop

1. **Comment** the outcome through the gate with `jira-comment.py`. If the board has
   `public_comments = true`: short, outcome and user-facing link only, no PR links or
   internals. Otherwise the PR link and a short technical note are fine.
2. **Transition**: `jira-transition.sh PROJ-123 --to Done` once the work is delivered
   (merged and applied, or as the board defines done). Not delivered yet: leave it in
   progress and say what is pending.
3. **Return the worktree** after the branch is pushed (`git-worktrees`).
4. **Time tracking**: run the board's `[time_tracking]` skill if one is configured.
   Never write a Jira worklog unless asked.

## Report

End with: ticket URL and status, branch and PR URL, what was applied or is waiting for
approval (with the command block), and anything the user still has to do.
