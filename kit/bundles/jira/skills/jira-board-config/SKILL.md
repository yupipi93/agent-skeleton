---
name: jira-board-config
description: "Template and lookup for per-board Jira settings (project key, issue and request types, title format, transitions, assignee and reporter, public comments, routing). Use before creating, commenting on or transitioning a ticket on a board, or when the user wants to describe a new Jira board."
---

# Jira board config

The jira scripts are generic; what differs per board lives in a small TOML file the user
fills once. Boards are company data, so they never go in the public kit.

## Where board files live

Look in this order and use the first match for the project key:

1. `local/bundles/*/jira-boards/<KEY>.toml` (a private bundle, can be versioned in a
   company repository)
2. `~/.config/agent-skeleton/jira-boards/<KEY>.toml` (personal, outside any repo)

No file for the board: use the defaults in `atlassian.env`, discover what you need
(below), and offer to write the file for the user from the template.

## Template

Copy `kit/bundles/jira/skills/jira-board-config/assets/board.example.toml` and fill it.
Every key is optional except `project`.

| Key | Meaning |
|---|---|
| `project`, `name`, `kind` | Key (`PROJ`), display name, `software` or `service_desk` |
| `issue_types`, `default_issue_type` | Allowed types and the one for new tickets |
| `[request_types]` | Service desk only: name to request type id (sent with `--request-type`) |
| `[titles]` | `format` such as `"[{component}] {title}"`, `max_words`, valid `components` |
| `[people]` | `assignee` and `reporter`: `me`, an accountId, `deduce`, or empty; `reporter_fallback`; `owners_file` (CODEOWNERS or a module to owner table) |
| `public_comments` | `true` when requesters or customers read every comment; `comment_language` |
| `[comments.start]` | The "we are on it" comment posted once when work starts, per language (`en`, `es`); a standing, pre-approved template |
| `[links]` | `style` `browse` or `portal` (service desk customers cannot open `/browse/`), `portal_id` |
| `[transitions]` | Status names `start`, `done`, `cancel`, `waiting` (blocked on someone outside the team, rule `jira-waiting-status`); `done_needs_hop` |
| `[routing]` | Signals (repo names, keywords) that send new work to this board |
| `[time_tracking]` | Optional: the skill or command to run after Done |

## Using it

- **Create**: pass `--project`, `--issuetype`, `--request-type`, `--assignee`,
  `--reporter` or `--reporter-email` from the file to
  `kit/bundles/jira/scripts/jira-create.sh`, and build the summary from `[titles]`.
- **Reporter `deduce`**: find the module's owner in `owners_file` (first owner wins),
  pass their email with `--reporter-email`; fall back to `reporter_fallback` and say so.
- **Comments**: `public_comments = true` means outcome and user-facing links only
  (rule `outbound-text-safety`). `[comments.start]` is sent verbatim when work starts
  (`jira-tickets`, "Picking a ticket up").
- **Links for people outside the team**: with `[links] style = "portal"` set
  `JIRA_LINK_STYLE=portal` and `JIRA_PORTAL_ID` so the scripts print portal URLs.
- **Transitions**: `kit/bundles/jira/scripts/jira-transition.sh` resolves names itself;
  the file documents the path for humans and for `--to` values.

## Discovering a board's values

```bash
kit/bundles/jira/scripts/jira-search.sh 'project = PROJ ORDER BY created DESC' --max 5
kit/bundles/jira/scripts/jira-issue.sh PROJ-123 --json      # issue type, request type field
kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --list  # transition names and ids
```

A service desk request type id shows in the issue JSON under the request type field
(`JIRA_REQUEST_TYPE_FIELD`, usually `customfield_10010`).

## Richer boards

When a board needs prose (who files what, naming habits, escalation), create a private
skill next to the file: `bin/skeleton new-skill <private-bundle> jira-board-<key>`, keep
the TOML as the source of values, and describe only the judgement calls in the skill.
