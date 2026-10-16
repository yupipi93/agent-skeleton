---
description: Never run terraform apply or destroy without the user's explicit approval of that exact change; plan freely, summarize, then ask.
apply: always
---

# Terraform apply requires approval

**Do not run `terraform apply` or `terraform destroy` (with or without
`-auto-approve`), or any wrapper that applies non-interactively, unless the user has
explicitly approved that exact apply in this conversation.**

Free to run without asking: `fmt`, `validate`, `init`, `plan`, `show`, `output`,
`state list` / `state show`, `workspace list|show`, `providers`, `graph`.

Ask first, because they rewrite state even though they do not touch resources:
`import`, `state mv`, `state rm`, `state push`, `force-unlock` (skill
`terraform-import-and-state`).

How to hand over an apply:

1. Run `terraform validate`, then `terraform plan` (save it with `-out` when the user
   may want to apply exactly that plan).
2. Summarize the plan: counts, every destroy or replace first, drift you did not
   cause (skill `terraform-plan-review`).
3. Give a copy-paste block with the workspace and the minimal `-target` set, and ask
   "Apply now?". Wait for an explicit yes.
4. An approval covers that plan, workspace and target set only. A changed plan, a
   different environment or a re-plan with new changes needs a new approval.
5. Never apply a whole workspace that shows drift unrelated to the task, never use
   `-lock=false` for an apply, and never `force-unlock` a lock you did not create.
