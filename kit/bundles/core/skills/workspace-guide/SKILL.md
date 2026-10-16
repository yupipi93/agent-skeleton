---
name: workspace-guide
description: Where things live in an agent-skeleton workspace and how to change them. Use when creating, moving or editing a skill, rule, hook, MCP server, bundle or setting, when a skill or rule does not show up in a tool, or when asked "where do I put this".
---

# Workspace guide

The kit is the only source of truth. Every tool-facing file is generated from it by
`bin/skeleton init`, so editing a generated file is always the wrong move: it is
overwritten or pruned on the next run.

## Where to write

| You want to add or change | Write it in | Then |
|---|---|---|
| A skill | `kit/bundles/<b>/skills/<name>/SKILL.md` (or `bin/skeleton new-skill <b> <name>`) | `bin/skeleton init && bin/skeleton check` |
| A rule | `kit/bundles/<b>/rules/<name>.md` with `description` + `apply` frontmatter | same |
| A hook | `kit/bundles/<b>/hooks.toml` + an executable in `kit/bundles/<b>/scripts/` | same |
| An MCP server | `kit/bundles/<b>/mcp.toml` | same |
| A whole new bundle | `kit/bundles/<b>/bundle.toml` (+ `Brewfile` group, + `docs/bundles/<b>.md`) | same |
| Something private | the same shapes under `local/bundles/<b>/` (git-ignored) | same |
| A personal toggle | `bin/skeleton enable|disable <name>` (edits `skeleton.local.toml`) | automatic |
| Tool settings | `kit/tool-config/<tool>/settings.json`, or `[settings.<tool>]` in `skeleton.local.toml` | `bin/skeleton init` |

Never write into `CLAUDE.md`, `.claude/`, `.cursor/`, `.gemini/`, `.agents/`, `.mcp.json`
or `.skeleton/`. Personal Claude Code settings belong in `.claude/settings.local.json`,
which the generator never touches.

## What gets generated

- Skills: symlinked into `.claude/skills/` (Claude Code) and `.agents/skills/` (Cursor,
  Gemini CLI, Antigravity). An invocation override renders a patched copy under
  `.skeleton/rendered-skills/` and links that instead.
- Rules: rendered per tool (`.cursor/rules/*.mdc`, `.claude/rules/*.md`,
  `.agents/rules/*.md`, `.gemini/RULES.md`), because each tool wants different frontmatter.
- Hooks and MCP: one file per tool, never shared between two tools.
- User-invocable skills (`disable-model-invocation: true`) also get a Gemini CLI command
  in `.gemini/commands/<name>.toml`.

Details per tool: `docs/tool-support.md`.

## When something does not show up

1. `bin/skeleton list` shows whether the bundle and the skill are on.
2. `bin/skeleton doctor` reports a stale generated tree; fix it with `bin/skeleton init`.
3. `bin/skeleton check` catches a skill whose `name` differs from its folder (Cursor and
   the Agent Skills spec drop those) and frontmatter that strict YAML parsers reject.
4. Restart or reload the tool; most read skills and rules at session start.

## Scripts

Skills call scripts by repo-root-relative path, run from the repository root:
`kit/bundles/<b>/scripts/<script> <args>`. Shared helpers live in
`kit/bundles/core/scripts/lib/` (`envfile.py` for config files, `secrets.sh` for curl
calls that keep secrets off the command line, `secret-patterns.txt` for the text guard).

## Projects

Repositories are linked, never copied: `bin/skeleton projects add <name>` symlinks
`<projects_dir>/<name>` into `projects/` with fuzzy matching and refreshes
`agent-skeleton.code-workspace`. `projects remove` deletes only the symlink.

## Result line for commands

User-invocable skills end with one short line that signals the outcome:

| Outcome | Format |
|---|---|
| Success | `✅ **subject** what happened` |
| Warning | `⚠️ **subject** why it was skipped` |
| Error | `❌ **subject** what went wrong` |
| Removal | `🗑️ **subject** confirmation` |
