# Agent instructions (shared by every tool)

This repository is an **agent-skeleton** workspace: one kit of skills, rules, hooks and
MCP servers, rendered by `bin/skeleton init` for Claude Code, Cursor, Gemini CLI and
Antigravity. This file is the shared entrypoint; every tool reads it.

## Layout

| Path | What it is | Who writes it |
|---|---|---|
| `kit/bundles/<bundle>/` | Source of truth: `bundle.toml`, `skills/`, `rules/`, `hooks.toml`, `mcp.toml`, `scripts/` | You (kit changes) |
| `local/bundles/<bundle>/` | Private bundles, same shape, git-ignored | You (private changes) |
| `kit/tool-config/<tool>/` | Per-tool settings templates | You |
| `skeleton.toml` / `skeleton.local.toml` | Committed defaults / personal overrides | You, or `bin/skeleton enable/disable` |
| `projects/<name>` | Symlinks to the user's repositories | `bin/skeleton projects add` |
| `plans/` | Plan files, `*.plan.md` | Agents |
| `docs/` | Architecture, customization, tool support, decisions | You |
| `CLAUDE.md`, `.claude/`, `.cursor/`, `.gemini/`, `.agents/`, `.mcp.json`, `.skeleton/` | **Generated**, git-ignored | `bin/skeleton init` only |

## Where to write configuration

- Write skills, rules, hooks and MCP specs **only** in `kit/bundles/<b>/` or `local/bundles/<b>/`.
- **Never edit a generated path.** It is overwritten or pruned on the next `bin/skeleton init`.
- After changing anything under `kit/`, `local/` or the manifests, run `bin/skeleton init`,
  then `bin/skeleton check`.
- New skill: `bin/skeleton new-skill <bundle> <name>`. The `skill-authoring` skill has the rules.

## Script path convention

Skills and hooks refer to scripts by their **repo-root-relative path**, and agents run them
from the repository root, for example `kit/bundles/core/scripts/text-guard.sh --file draft.md`.
Scripts accept environment variables for every config key they read and never take secrets
as command-line arguments.

## Safety gates (they override autonomy)

These gates are rules shipped with their bundles. When a gate applies, it wins over every
instruction to act autonomously, and an approval covers only the exact action approved.

| Gate | Bundle | In short |
|---|---|---|
| `agent-safety-gates` | core | Index of the gates and their precedence |
| `permission-prompt-hygiene` | core | Batch prompted commands; never disguise a command to dodge a prompt |
| `no-broad-process-kill` | core | Kill only PIDs you started; never `pkill`/`killall` by pattern |
| `worktree-for-project-writes` | git | Write to `projects/<repo>` only from your own worktree |
| `outbound-text-safety` | jira | Secret scan and user approval before text leaves the machine |
| `terraform-apply-requires-approval` | terraform | Plan freely; apply only after an explicit yes |
| `database-mutation-requires-approval` | gcp | Read-only SQL freely; mutations only after an explicit yes |

A gate whose bundle is disabled is not loaded; follow the intent anyway when the situation arises.

## Working style

- Bias for action: research, implement and validate end to end without asking for routine
  permission. Run the relevant checks (tests, linters, `bin/skeleton check`) before reporting.
- Ask **one focused question only when a requirement is critically underspecified**. When
  several reasonable paths exist, pick the most idiomatic one and say which.
- Prefer additive, reversible changes. Destructive operations need an explicit request.
- Never commit secrets (`.env`, tokens, keys, credential files).
- Plans go in `plans/<topic>.plan.md` (skill `plan-files`).

## Commits

Conventional Commits: `<type>(<scope>): <description>`, with types `feat`, `fix`, `docs`,
`style`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`. Stage explicit paths, never
`git add -A` in a checkout that may hold someone else's work.
