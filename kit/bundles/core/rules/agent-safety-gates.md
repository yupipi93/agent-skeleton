---
description: Index of the safety gates shipped by the kit and their precedence over autonomy.
apply: always
---

# Safety gates override autonomy

Some actions need the user's explicit approval or a specific procedure, whatever the
autonomy level of the session. When a gate applies, it wins over "act without asking".

| Gate | Bundle | Rule |
|---|---|---|
| Infrastructure apply | terraform | `terraform-apply-requires-approval`: plan freely, apply only after an explicit yes |
| Database mutation | gcp | `database-mutation-requires-approval`: read-only queries freely, writes only after an explicit yes |
| Outbound text | jira | `outbound-text-safety`: secret scan and approval before text reaches a ticket, PR or chat |
| Shared checkouts | git | `worktree-for-project-writes`: write to `projects/<repo>` only from your own worktree |
| Process control | core | `no-broad-process-kill`: kill only the PIDs you started |
| Permission prompts | core | `permission-prompt-hygiene`: batch prompted commands, never disguise them |

How to apply a gate:

1. Show the exact action (command, statement, text) and its target before running it.
2. Wait for an explicit approval of **that** action. An approval does not carry over to a
   different action, target or environment.
3. After running it, report the real result, not just "done".

If a gate's bundle is disabled, its rule is not loaded, but the intent still holds.
