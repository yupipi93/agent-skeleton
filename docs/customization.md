# Customization and the bundle contract

## Personal overrides: `skeleton.local.toml`

Git-ignored, deep-merged over `skeleton.toml`. Every table is optional; the annotated
example is [`skeleton.local.example.toml`](../skeleton.local.example.toml).

| Table / key | Effect |
|---|---|
| `tools = [...]` | Tools to render for (`claude`, `cursor`, `gemini`, `antigravity`) |
| `[user] name, language` | Optional generated rule `skeleton-user-profile` (name, reply language) |
| `[paths] projects_dir` | Where `projects add` looks (default `~/code`) |
| `[bundles] <b> = bool` | Bundle on or off |
| `[skills] "<s>" = bool` | Skill on or off, overriding its bundle |
| `[skills] "<s>" = { enabled = bool, invocation = "user"\|"model"\|"auto" }` | Toggle and invocation override (rendered copy) |
| `[rules] "<r>" = bool` | Rule on or off (file name without `.md`) |
| `[hooks] "<id>" = bool` | Hook on or off |
| `[overrides] "<s>" = "path"` | Link your own fork of a kit skill instead of the kit copy |
| `[mcp.<name>]` | Override fields of a kit MCP server, `enabled = false`, or declare your own server |
| `[settings.claude]`, `[settings.gemini]` | Keys deep-merged into the generated settings files |

Precedence, lowest to highest: `bundle.toml` `default_enabled`, `skeleton.toml`,
`skeleton.local.toml`; for a skill, rule or hook, an explicit entry beats its bundle state
(so you can enable one skill of a disabled bundle).

`bin/skeleton enable|disable <name>` edits this file with a minimal TOML writer that keeps
comments and unrelated content, removes the key again when the value returns to its
default, and re-runs `init`. Names resolve in the order bundle, skill, rule, hook; use
`--kind` when two share a name.

## Private bundles: `local/bundles/<b>/`

Same shape as a kit bundle, git-ignored, discovered automatically and **on by default**
(`[bundles] <b> = false` turns one off). A local bundle with the same name as a kit bundle
replaces it. Typical use: clone a private repository of company skills there.

```bash
git clone git@github.com:acme/agent-bundle.git local/bundles/acme
bin/skeleton init
```

`bin/skeleton check` validates local bundles' structure, but not the kit's text rules
(em dash, denylist), which only apply to the public kit.

## Bundle layout

```text
kit/bundles/<bundle>/
├── bundle.toml          # required
├── skills/<skill>/SKILL.md (+ references/, assets/)
├── rules/<rule>.md      # neutral frontmatter
├── hooks.toml           # optional
├── mcp.toml             # optional
├── scripts/             # executables used by skills and hooks (never a top-level bin/)
└── setup.sh             # optional interactive config wizard, run by `bin/skeleton setup <b>`
```

Also add the bundle's Homebrew entries under a `# group: <bundle>` marker in the
`Brewfile`, and a page `docs/bundles/<bundle>.md`.

### `bundle.toml`

```toml
name = "jira"                      # required, equals the folder name
title = "Jira"                     # required, human title
emoji = "🎫"                       # required, shown by `list` and in docs
description = "One line."          # required
version = "0.1.0"                  # optional
default_enabled = true             # optional, default false (local bundles: true)
requires = ["core"]                # optional, other bundle names; warned when off
brew = ["jq"]                      # optional, Homebrew formulae/casks (must be in the Brewfile)
commands = ["curl", "python3"]     # optional, executables `doctor` requires on PATH
optional_commands = ["jq"]         # optional, executables `doctor` reports as info
config_files = ["~/.config/agent-skeleton/atlassian.env"]   # optional, `doctor` checks existence and mode 0600
```

### Skill frontmatter

```yaml
---
name: jira-tickets                 # required, equals the folder, [a-z0-9-], <= 64 chars
description: "What it does. Use when ..."   # required, 1..1024 chars, aim <= 300
disable-model-invocation: true     # optional: user-invocable command (slash menu only)
user-invocable: false              # optional: model-only, hidden from the slash menu
---
```

Skills with `disable-model-invocation: true` also get `.gemini/commands/<name>.toml`.
Quote `description` when it contains `: `. Keep `SKILL.md` under 500 lines.

### Rule frontmatter

```yaml
---
description: Never run terraform apply without explicit user approval.   # required
apply: always          # required: always | glob | manual
globs: ["**/*.tf"]     # required when apply: glob (inline or block list)
---
```

Keep always-on rules under 2 KB; long material goes in a skill. Rules whose loading
should depend on the model's judgement are skills, not rules.

### `hooks.toml`

```toml
[[hook]]
id = "voice-summary-stop"          # required, unique across bundles
event = "stop"                     # session_start | prompt_submit | before_tool | after_tool | stop | session_end
run = "scripts/voice-note-hook.py" # required, bundle-relative, executable
timeout_s = 20                     # optional, default 30 (Gemini gets milliseconds)
tools = ["claude", "cursor"]       # optional subset of tools
match = { mcp = "atlassian.*" }    # optional, tool events only: { mcp = "<server regex>" } | { shell = true } | { tool = "Edit|Write" }
args = ["--mode", "context"]       # optional extra arguments
fail_closed = true                 # optional, Cursor failClosed
description = "Text shown by Gemini CLI"   # optional
```

Rendered command: `<prefix><repo-relative path> [args...] --client <tool>`, with prefix
`"$CLAUDE_PROJECT_DIR"/` (Claude), `"$GEMINI_PROJECT_DIR"/` (Gemini) or `./` (Cursor,
Antigravity). **Hook script contract:**

- accept `--client claude|cursor|gemini|antigravity` (and ignore unknown flags);
- read the event JSON on stdin; exit 2 to block, 0 to allow; never crash on bad input;
- print tool-specific JSON only when needed (`core/scripts/text-guard.sh` shows the
  pattern: Cursor `{"permission": ...}`, Gemini `{"decision": ...}`);
- filter by MCP server or tool name yourself: Cursor's MCP and shell events are not
  matcher-scoped by the renderer;
- exit fast and silently when the bundle is not configured (missing config file).

### `mcp.toml`

```toml
[server.my-server]
command = "npx"                    # stdio server ...
args = ["-y", "my-mcp@1.2.3"]
env = { API_TOKEN = "${MY_TOKEN}" }
cwd = "${SKELETON_ROOT}"           # optional
tools = ["claude", "cursor"]       # optional subset

[server.remote]
url = "https://mcp.example.com/mcp"   # ... or a remote server
type = "http"                      # http (default) | sse
headers = { Authorization = "Bearer ${MY_TOKEN}" }
```

`${VAR}` stays an environment reference (Cursor gets `${env:VAR}`); `${SKELETON_ROOT}`
becomes the absolute checkout path; a leading `~/` in `command` is expanded. Never put
secrets or machine paths in `mcp.toml`; machine paths go in `skeleton.local.toml`
`[mcp.<name>]`.

## Scripts

- Path convention: skills cite scripts repo-root-relative, `kit/bundles/<b>/scripts/<x>`.
  `bin/skeleton check` warns when a cited `kit/bundles/...` path does not exist.
- Shell: bash 3.2 compatible (no `mapfile`, associative arrays, `${x,,}`, `$'\u...'`).
- Python: stdlib only. Keep bundle scripts runnable on Python 3.9 (macOS system
  `python3`) unless they re-exec like `bin/skeleton` does.
- Config: KEY=VALUE files under `~/.config/agent-skeleton/` (0600, directory 0700), read
  with `kit/bundles/core/scripts/lib/envfile.py get FILE KEY` (env var KEY wins), never
  `source`d. Secrets go to `envfile.py set FILE KEY` on stdin, never on argv.
- HTTP with secrets: source `kit/bundles/core/scripts/lib/secrets.sh` and use
  `secrets_curl_basic`, `secrets_curl_bearer` or `secrets_curl_header` (credentials reach
  curl through `-K -` on stdin).
- Outbound text: run `kit/bundles/core/scripts/text-guard.sh --file <draft>` (or
  `lib/secretscan.py` from Python) before sending anything to a ticket, PR or chat.
- Nothing is sent anywhere without an explicit flag or user action.

## Tool settings

- `kit/tool-config/claude/settings.json`: Claude Code template (`$schema`, a
  conservative read-only allowlist, denies for destructive commands, `plansDirectory`).
  `init` adds hooks and `skillOverrides`.
- `kit/tool-config/gemini/settings.json`: Gemini CLI template (`context.fileName`
  includes `AGENTS.md` and `.gemini/RULES.md`). `init` adds hooks, `mcpServers` and
  `skills.disabled`.
- Personal Claude settings go in `.claude/settings.local.json` (never generated).
