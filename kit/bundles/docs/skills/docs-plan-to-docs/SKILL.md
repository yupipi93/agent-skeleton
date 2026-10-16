---
name: docs-plan-to-docs
description: "Turn a finished .plan.md into the target project's structured docs (ADR, guide, module README, architecture state), update the indexes, then delete the plan. Use as a slash command with the plan path."
disable-model-invocation: true
---

# Plan to docs

Convert a `*.plan.md` file into the documentation system of the project it belongs to,
so the knowledge outlives the plan, then delete the plan to avoid a stale duplicate.

## Arguments

The plan file path, given after the command name (`$ARGUMENTS` in Claude Code,
`{{args}}` in Gemini CLI). Without one, use the plan open in the editor or the most
recent file in `plans/`; if that is ambiguous, ask which plan.

## Steps

### 1. Identify the target project and its docs root

- Read the plan and decide which repository it describes, usually one under
  `projects/<repo>`.
- **Infrastructure first**: when the plan touches infrastructure, environment settings
  or deployed services, the target is the **IaC repository**, not the application repo
  or this workspace.
- Find the docs root (`docs/` by default; follow the repo's own layout if it differs).
- **Writes to a project repo happen in your own worktree on a branch**, never in the
  shared checkout (rule `worktree-for-project-writes`, skill `git-worktrees`, when the
  git bundle is on).
- If the project cannot be identified with certainty, ask one question.

### 2. Classify the content

One plan often yields several documents:

| Category | Destination (under `docs/`) | Holds |
|---|---|---|
| Architecture decision | `adr/` | Why, what was decided, alternatives, trade-offs |
| Procedure | `guides/` | Step-by-step instructions |
| Infrastructure state | `architecture/` | What exists now |
| Module specific | `modules/<module>/` | One component's README |
| External system | `external/` | Systems outside the repo |

### 3. Merge before you create

Read `docs/README.md` (or the index) and search existing docs for the same topic,
resources or decision. Merge into an existing document instead of creating a
duplicate; link to or update a related ADR.

### 4. Prepare folders

Create `docs/adr/`, `docs/guides/`, `docs/architecture/` if missing, and
`modules/`, `external/`, `standards/` only when the plan needs them. Documentation
only: never create source, settings or infrastructure folders here.

### 5. Write the documents

- **ADR**: next sequential number `NNNN` in `docs/adr/`, the repo's ADR template (or
  the one in skill `iac-docs-maintenance`). Status **Accepted** if every plan task is
  done, **Proposed** if some are pending, **Superseded by ADR-XXXX** when replaced.
- **Guide**: `docs/guides/<topic>-guide.md`: actionable steps, commands, config
  examples, verification. Planning context (order of work, line numbers) is dropped;
  rationale moves to the ADR.
- **Module README**: update `docs/modules/<module>/README.md` (create it if needed).
- **Architecture**: describe the current state only; history goes to the ADR.

Rules: never duplicate content (link with relative paths such as
`../guides/setup.md`); turn "edit file X" into "configured service Y to do Z"; no
secrets or personal data.

### 6. Update indexes

Link every new or renamed doc from `docs/README.md` and from sub-indexes such as
`docs/adr/README.md` when they exist. Check that each relative link resolves.

### 7. Delete the plan

1. Confirm every section of the plan landed in at least one document.
2. Delete the plan file. Leave its folder in place even if it is now empty.

### 8. Report

- Documents created or updated, with paths.
- How the plan's content was classified.
- Anything merged into an existing document instead of duplicated.
- The deleted plan path.

End with one line:

| Outcome | Line |
|---|---|
| Success | ✅ **plan-to-docs** \<plan\> became \<n\> docs in \<repo\>/docs; plan deleted. |
| Partial | ⚠️ **plan-to-docs** \<n\> docs written; plan kept because \<section\> has no home yet. |
| Error | ❌ **plan-to-docs** failed at \<step\>: \<reason\>. |
