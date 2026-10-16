---
name: git-conventional-commits
description: "Write and check Conventional Commits messages from the staged or unstaged diff. Use when the user asks for a commit message, commit review or cleanup, or mentions conventional commits, feat/fix/chore, breaking changes, semantic versioning or changelog-friendly commits."
---

# Conventional commits

Use this skill to produce commit messages that follow Conventional Commits 1.0.0.

## Goal

Write commit messages in this structure:

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Keep the first line concise and meaningful. Focus on intent and impact, not a file-by-file dump.

## Commit Type Selection

Choose the most accurate type:

- `feat`: introduces a new feature.
- `fix`: patches a bug.
- `docs`: documentation-only changes.
- `style`: formatting/style-only changes (no logic change).
- `refactor`: code restructuring without behavior change.
- `perf`: performance improvement.
- `test`: test additions/updates.
- `build`: build system or dependency changes.
- `ci`: CI/CD workflow changes.
- `chore`: maintenance work that does not fit other types.
- `revert`: reverts a previous commit.

When multiple unrelated changes exist, suggest splitting into multiple commits.

## Scope Rules

- Scope is optional, but recommended when it clarifies context.
- Use a short noun in lowercase (examples: `api`, `auth`, `ui`, `terraform`, `deps`).
- Prefer one scope per commit.

Examples:

- `feat(auth): add OIDC login flow`
- `fix(api): handle empty pagination cursor`
- `chore(deps): update eslint and typescript`

## Description Rules

- Use imperative mood (e.g., "add", "fix", "remove").
- Keep it short (roughly <= 72 chars when practical).
- Start lowercase unless a proper noun requires uppercase.
- Avoid trailing period.
- Describe what changed and why at a high level.

## Breaking Changes

Mark breaking changes with one of:

1. `!` after type/scope:
   - `feat(api)!: remove v1 endpoints`
2. `BREAKING CHANGE:` footer:
   - `BREAKING CHANGE: v1 endpoints were removed; migrate to /v2`

Use both when extra clarity is useful.

## Body and Footer Guidance

Add a body when context is necessary:

- Why the change was needed.
- Trade-offs or migration notes.
- Important behavioral details.

Add footers when needed:

- `BREAKING CHANGE: ...`
- `Refs: #123`
- `Closes: #123`
- `Refs: PROJ-123` for a ticket key

## Workflow

1. Inspect staged and unstaged changes (`git diff --cached`, `git diff`, `git log --oneline -10` to match the repo's style).
2. Infer the primary intent of the change.
3. Pick type and optional scope.
4. Draft 1-3 candidate commit subjects.
5. If requested, provide full message with body/footers.
6. Validate against Conventional Commits checklist before finalizing.

## Validation Checklist

Before finalizing, confirm:

- Prefix format is valid: `<type>[scope]: <description>`.
- Type matches the actual change.
- Scope is concise and relevant (if present).
- Description is imperative, concise, and specific.
- Breaking changes are explicitly marked.
- Body/footers are only included when they add value.

## Output Template

When proposing a single final message, use:

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

When proposing alternatives, use:

```text
Option 1: <type>[scope]: <description>
Option 2: <type>[scope]: <description>
Option 3: <type>[scope]: <description>
```

## Quick Examples

```text
feat(search): add filters for owner and status
```

```text
fix(terraform): prevent null values in run service vars
```

```text
refactor(api): split user sync handler by provider
```

```text
feat(api)!: remove legacy v1 billing route

BREAKING CHANGE: clients must migrate to /api/v2/billing
```

## Committing

- Stage explicit paths (`git add path/a path/b`), never `git add -A` in a checkout that
  may hold someone else's work.
- Never commit secrets (`.env`, keys, tokens, credential files).
- Put the ticket key in the subject scope only when the repo does that; otherwise use a
  `Refs:` footer.

## Reference

Conventional Commits specification:
https://www.conventionalcommits.org/en/v1.0.0/
