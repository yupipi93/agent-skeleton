---
name: ticket
description: "Slash command: run the full ticket lifecycle for a Jira key (PROJ-123) or a task description: read or create the ticket, worktree branch, change, PR, client-safe comment, transition."
disable-model-invocation: true
---

# /ticket

Run the end-to-end ticket lifecycle on the text after the command:

- a Jira key (`/ticket PROJ-123`): **inbound**, read the ticket and resolve it;
- a description (`/ticket rotate the staging TLS certificate`): **outbound**, propose
  and create the ticket first, then resolve it.

## Steps

1. Load and follow the `devops-ticket-workflow` skill. Use `jira-board-config` for the
   board's values and `jira-tickets` for the scripts and text formats.
2. Keep the invariants on every run:
   - outbound text gate on every Jira, PR or chat write (rule `outbound-text-safety`);
   - Jira through `kit/bundles/jira/scripts/` (rule `jira-cli-first`);
   - branch in a worktree before the first edit, PR after (rule
     `worktree-for-project-writes`, skill `git-branch-pr-workflow`);
   - no `terraform apply` or other mutating cloud command without an explicit yes.
3. Adapt the order to the situation, never the invariants.
4. No Jira config yet (exit code 3 from a script): tell the user to run
   `bin/skeleton setup jira` and stop.

## Result line

End with exactly one of:

- `✅ PROJ-123 resolved: PR <url>, comment added, moved to <status>.`
- `✅ PROJ-123 created: <url>.`
- `⚠️ PROJ-123 paused: <what is missing>; next step: <step>.`
- `❌ Ticket run failed at <step>: <reason>.`
