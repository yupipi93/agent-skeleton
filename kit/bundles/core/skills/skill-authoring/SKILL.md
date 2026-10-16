---
name: skill-authoring
description: How to write a good agent skill for this kit (frontmatter, trigger-rich description under 300 chars, structure, references, slash-command skills, validation). Use when creating, reviewing, renaming or splitting a skill, or when a skill is not triggering.
---

# Skill authoring

A skill is a folder with a `SKILL.md` that follows the Agent Skills format, so the same
file works in Claude Code, Cursor, Gemini CLI and Antigravity.

## Start from the scaffold

```bash
bin/skeleton new-skill <bundle> <name>                    # model-invoked skill
bin/skeleton new-skill <bundle> <name> --user-invocable   # slash-command style
```

## Frontmatter

```yaml
---
name: terraform-plan-review          # required, must equal the folder name
description: "Review a terraform plan ... Use when ..."   # required
disable-model-invocation: true       # optional: slash command only
---
```

- `name`: kebab-case `[a-z0-9-]`, at most 64 characters, no leading, trailing or double
  hyphen, and **identical to the folder name**. Cursor and the spec drop skills that differ.
- `description`: 1 to 1024 characters, **aim for at most 300**. Tools list every
  description in the context window, so this is the budget that decides whether the skill
  is picked. Say what it does, then "Use when ..." with the phrases a user would type.
- Quote the description with double quotes when it contains `: `. Some tools parse
  frontmatter with a strict YAML parser and silently drop the skill otherwise.
- Keep other fields to what the tools document: `disable-model-invocation`,
  `user-invocable`, `allowed-tools`, `license`, `metadata`.

## Body

- Lead with the outcome in one or two sentences, then "When to use", "Steps", "Gotchas".
- Write steps as commands the agent can run, with repo-root-relative script paths:
  `kit/bundles/<b>/scripts/<script>.sh PROJ-123`.
- Keep `SKILL.md` **under 500 lines**. Move long material to `references/<topic>.md`,
  templates to `assets/`, and link them from the body. The agent reads them on demand.
- No personal data: placeholders such as `you@example.com`, `example.com`,
  `my-project-id`, `PROJ-123`, `~/` paths.
- Plain ASCII punctuation; the kit bans the em dash character (U+2014).
- One skill, one job. Split when the description needs two unrelated "Use when" clauses.

## Slash-command skills

Commands are skills with `disable-model-invocation: true`. Claude Code and Cursor show
them in the slash menu and never auto-load them; `bin/skeleton init` also renders
`.gemini/commands/<name>.toml` for Gemini CLI; Antigravity treats every skill as a
command. Users can flip any skill per machine:

```toml
# skeleton.local.toml
[skills]
"plan-files" = { invocation = "user" }   # user | model | auto
```

End a command skill with a single result line (`✅` / `⚠️` / `❌` / `🗑️`).

## Rules or skill?

A rule is always loaded (or loaded for matching files) and costs context in every
session: keep it under 2 KB and only for hard constraints. Everything procedural, or
anything the model can decide to load from a description, is a skill.

## Validate

```bash
bin/skeleton check     # name == folder, description length, line count, em dash, frontmatter
bin/skeleton init      # expose it to every tool
bin/skeleton list      # confirm it is on
```

`check` also warns when a skill references a `kit/bundles/...` path that does not exist.
