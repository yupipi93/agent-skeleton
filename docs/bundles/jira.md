# 🎫 jira

On by default. Jira Cloud through small REST scripts instead of an MCP server: read a
ticket with every comment and its Attached forms, create issues with rich descriptions,
comment, transition safely, and keep secrets out of everything you send.

## Skills

| Skill | Use it for |
|---|---|
| `jira-tickets` | The script table, reading a ticket properly, propose-then-create, the visual description template, closing the loop after a task, rewording around the text guard |
| `jira-board-config` | The per-board TOML template (project, issue and request types, title format, assignee and reporter, `public_comments`, transitions, routing) and where to keep it |
| `devops-ticket-workflow` | The end-to-end lifecycle: read ticket and forms, choose the repo, worktree branch, change, plan, PR, client-safe comment, transition |
| `ticket` | Slash command: `/ticket PROJ-123` or `/ticket <description>` runs that lifecycle |

## Rules (always on)

| Rule | In short |
|---|---|
| `outbound-text-safety` | Draft, secret-scan, show the exact text and destination, wait for approval, then send; public boards get outcome-only comments |
| `jira-cli-first` | Use the REST scripts; an MCP server only when no script covers the need, after asking |

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/jira/scripts/jira-issue.sh` | Header, description, attachments and **all** comments (paged), as Markdown; `--meta`, `--comments`, `--json` |
| `kit/bundles/jira/scripts/jira-search.sh` | JQL via `/rest/api/3/search/jql`, Markdown table; `--max`, `--json` |
| `kit/bundles/jira/scripts/jira-create.sh` | Create with an ADF description rendered from Markdown; assignee and reporter defaults from config (`me`, an accountId, or empty); `--reporter-email`; `--dry-run` |
| `kit/bundles/jira/scripts/jira-comment.py` | Add or edit a comment, or replace the description, from Markdown (tables, code, panels, issue cards, mentions); `--dry-run` |
| `kit/bundles/jira/scripts/jira-transition.sh` | Move by status name with at most one announced hop; never reaches Done through a cancellation; `--list`, `--dry-run` |
| `kit/bundles/jira/scripts/jira-link.sh` | Link two issues; `--list-types`, `--dry-run` |
| `kit/bundles/jira/scripts/jira-forms.sh` | Attached forms (Jira Forms), which MCP scopes cannot read |
| `kit/bundles/jira/scripts/jira-forms-context.sh` | The `jira-forms-context` hook (see Hooks) |
| `kit/bundles/jira/scripts/jira-mcp-guard.sh` | The `jira-mcp-text-guard` hook (see Hooks) |
| `kit/bundles/jira/scripts/lib/atlassian.sh` | Shared config loader and `atl_request` (credentials through `curl -K -`) |
| `kit/bundles/jira/scripts/lib/adf.py`, `lib/jira_json.py` | Markdown to ADF and back; renderers, transition resolver, payload builder (unit tested offline) |

Exit codes: 0 ok, 2 usage, 3 missing config, 4 API error, 5 blocked by the text guard
(`jira-transition.sh`: 6 not reachable). Every script has `--help`.

## Hooks

| Hook | Event | Tools | What it does |
|---|---|---|---|
| `jira-forms-context` | prompt_submit | Claude Code, Gemini CLI | Jira keys in the prompt: fetch their Attached forms and add them as context, framed as untrusted user-supplied data. Silent unless the bundle is configured; at most 3 keys, about 12 s, `curl --max-time` per request. `JIRA_FORMS_HOOK=off` disables it, `JIRA_FORMS_HOOK_PROJECTS=PROJ,OPS` narrows it |
| `jira-mcp-text-guard` | before_tool | all | Runs the core text guard over Atlassian or Jira MCP tool calls (raw payload and decoded strings) and blocks secrets |

## Configuration

`bin/skeleton setup jira` asks for the values, reads the token without echo, writes
`~/.config/agent-skeleton/atlassian.env` with mode 0600, and checks the credentials with
`GET /rest/api/3/myself` only if you agree. Every key can also be an environment
variable; `ATLASSIAN_ENV_FILE` points at another file.

| Key | Meaning |
|---|---|
| `JIRA_SITE` | `your-org.atlassian.net` (required) |
| `JIRA_EMAIL`, `JIRA_API_TOKEN` | Atlassian account email and API token |
| `JIRA_DEFAULT_PROJECT`, `JIRA_DEFAULT_ISSUETYPE` | Create defaults (`Task` when unset) |
| `JIRA_DEFAULT_ASSIGNEE` | `me` (the token owner), an accountId, or empty for Jira's default |
| `JIRA_DEFAULT_REPORTER` | An accountId, or empty |
| `JIRA_REQUEST_TYPE_FIELD` | Service desk request type field (default `customfield_10010`) |
| `JIRA_LINK_STYLE`, `JIRA_PORTAL_ID` | `browse` (default) or `portal` links for service desk customers |
| `JIRA_CLOUD_ID` | Forms API; fetched from the site when unset, stored by setup |
| `JIRA_FORMS_HOOK`, `JIRA_FORMS_HOOK_PROJECTS` | Forms hook switch and project allowlist |
| `JIRA_HTTP_TIMEOUT` | Seconds per request (default 30) |

Board specifics live in TOML files, one per board, in a private bundle
(`local/bundles/<b>/jira-boards/<KEY>.toml`) or `~/.config/agent-skeleton/jira-boards/`.
Start from `kit/bundles/jira/skills/jira-board-config/assets/board.example.toml`.

## Examples

```bash
kit/bundles/jira/scripts/jira-issue.sh PROJ-123
kit/bundles/jira/scripts/jira-create.sh --project PROJ --summary "[api] Rotate staging cert" \
  --description-file desc.md --assignee me --dry-run
kit/bundles/jira/scripts/jira-comment.py PROJ-123 --comment "✅ Ready: https://app.example.com"
kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --to Done --dry-run
```

## Design notes

- No `jq` and no GNU `timeout`: JSON goes through small, tested Python helpers, and
  every request has `curl --max-time`, so the scripts work on a stock Mac.
- Credentials never touch argv: shell scripts pipe a curl config on stdin, the Python
  writer builds the header in memory. Request bodies therefore always go in a file.
- Board values are data the agent reads (TOML), not flags the scripts parse, so the
  scripts stay usable on Python 3.9 and boards stay private.
- The forms hook is enrichment, never a blocker: any failure means no output.

## Dependencies

`curl`, `python3` (3.9+ for the scripts). Nothing from Homebrew.
