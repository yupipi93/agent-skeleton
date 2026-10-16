---
name: plan-files
description: Store implementation plans as plans/<topic>.plan.md in the workspace (not in the tool's home folder) and rename auto-generated plan names. Use when entering plan mode, writing or saving a plan, or asked where plans live.
---

# Plan files

Plans live in the workspace so every agent and tool can find them, and they survive the
session.

## Location

- Default directory: `plans/` at the repository root (git-ignored in the kit, so personal
  plans never reach the public repo; remove the line from `.gitignore` to version them).
- Claude Code writes plans there because the settings template sets
  `"plansDirectory": "plans"`. To use another folder, set it per machine:

  ```toml
  # skeleton.local.toml
  [settings.claude]
  plansDirectory = "docs/plans"
  ```

  then run `bin/skeleton init`. Use the same folder from every tool.

## Naming

- Extension: always `*.plan.md`.
- Name: kebab-case, descriptive, `<area>-<topic>-<action>.plan.md`, for example
  `api-gateway-rate-limit-rollout.plan.md` or `docs-getting-started-rewrite.plan.md`.
- Tools often generate random names (`whimsical-sleeping-otter.md`). Rename such a file
  as soon as its topic is clear, and update any links to it.

## Content

1. Goal and context in a few lines.
2. Steps, each one verifiable.
3. Risks and the gates that apply (approvals for apply, database writes, outbound text).
4. Validation: how you will know it worked.

When the work is done, either delete the plan or turn its durable parts into docs
(architecture notes, decisions), then delete it. Stale plans mislead the next agent.

## Check

Any file in the plans directory that does not end in `.plan.md` is non-compliant:
rename it.
