# Tool support

What `bin/skeleton init` generates for each tool, and the tool quirks behind it
(state as of October 2026).

## Matrix

| Feature | Claude Code | Cursor | Gemini CLI | Antigravity |
|---|---|---|---|---|
| Instructions | `CLAUDE.md` (`@AGENTS.md`) | `AGENTS.md` (native) | `AGENTS.md` via `context.fileName` | `AGENTS.md` (native) |
| Skills | `.claude/skills/<s>` (link) | `.agents/skills/<s>` (link) | `.agents/skills/<s>` (link) | `.agents/skills/<s>` (link) |
| Rules, always | `.claude/rules/<r>.md` (no frontmatter) | `.cursor/rules/<r>.mdc` (`alwaysApply: true`) | `.gemini/RULES.md` (concatenated) | `.agents/rules/<r>.md` (`trigger: always_on`) |
| Rules, glob | `paths:` list | `globs: a,b` + `alwaysApply: false` | `.gemini/RULES.md`, "Scoped rules" section | `trigger: glob` + `globs: a,b` |
| Rules, manual | not rendered | description only | not rendered | `trigger: manual` |
| Slash commands | skills with `disable-model-invocation: true` | same | `.gemini/commands/<s>.toml` | every skill is a command |
| Hooks | `.claude/settings.json` `hooks` | `.cursor/hooks.json` (`version: 1`) | `.gemini/settings.json` `hooks` (timeouts in ms) | `.agents/hooks.json` |
| MCP | `.mcp.json` (`type`, `${VAR}`) | `.cursor/mcp.json` (`${env:VAR}`) | `.gemini/settings.json` `mcpServers` (`httpUrl`) | `.agents/mcp_config.json` (`serverUrl`) |
| Disabled skills | `skillOverrides: {"<s>": "off"}` | not linked | `skills.disabled` | not linked |
| Settings template | `kit/tool-config/claude/settings.json` | (UI) | `kit/tool-config/gemini/settings.json` | (UI / home only) |

## Hook events

| Neutral | Claude Code | Cursor | Gemini CLI | Antigravity |
|---|---|---|---|---|
| `session_start` | `SessionStart` | `sessionStart` | `SessionStart` | `SessionStart` |
| `prompt_submit` | `UserPromptSubmit` | `beforeSubmitPrompt` | `BeforeAgent` | not rendered |
| `before_tool` | `PreToolUse` | `preToolUse`, `beforeMCPExecution` (match mcp), `beforeShellExecution` (match shell) | `BeforeTool` | `PreToolUse` |
| `after_tool` | `PostToolUse` | `postToolUse`, `afterMCPExecution`, `afterShellExecution` | `AfterTool` | `PostToolUse` |
| `stop` | `Stop` | `stop` | `AfterAgent` | `Stop` |
| `session_end` | `SessionEnd` | `sessionEnd` | `SessionEnd` | not rendered |

Matchers for tool events: `match.mcp = "<re>"` becomes `mcp__<re>` for Claude Code and
`<re>` for Gemini CLI and Antigravity (Cursor uses the dedicated MCP event, the script
filters); `match.shell` becomes `Bash` (Claude) or `run_shell_command` (Gemini);
`match.tool` uses Claude Code tool names and is mapped best effort (Cursor `Shell`,
`Write`; Gemini `replace`, `write_file`, `read_file`).

## Notes per tool

### Claude Code

- Reads `CLAUDE.md`, which imports `AGENTS.md`. Recent versions also read `AGENTS.md`
  natively when no `CLAUDE.md` exists; the generated file keeps older versions working
  and is not read twice.
- `.claude/rules/*.md` only understands `paths:`; without it a rule is always loaded.
- Skills must be in `.claude/skills/`; Claude Code does not read `.agents/skills/`.
- Personal settings: `.claude/settings.local.json` (never generated).

### Cursor

- **Turn off "Third-party imports"** (Settings > Rules, "Include third-party plugins,
  skills and other configs", on by default). When on, Cursor also loads `.claude/`
  skills, `.claude/settings.json` hooks and `CLAUDE.md`: skills appear twice and Claude
  hooks run inside Cursor with `--client claude`. The kit assumes it is off.
- `.cursor/rules` only reads `.mdc` files. Skill `name` must equal the folder name.

### Gemini CLI

- Since mid-2026 Gemini CLI serves Gemini Code Assist Standard/Enterprise and paid API
  keys; free and Google AI Pro/Ultra users moved to Antigravity CLI (`agy`). The kit still
  renders for Gemini CLI; drop `gemini` from `tools` if you do not use it.
- Rules have no native format: always-on and scoped rules are concatenated into
  `.gemini/RULES.md`, loaded through `context.fileName`.
- Settings are validated strictly; keep `kit/tool-config/gemini/settings.json` to
  documented keys.

### Antigravity

- Reads `.agents/` (the legacy `.agent/` is not generated). Every rule file needs a
  `trigger:` frontmatter or it is silently ignored; the renderer always writes one.
- Limits: 24,000 bytes per rule file and about 20,000 tokens for all always-on rules.
- **Workflows are deprecated** (they stop working on 2026-10-19). The kit renders none:
  skills are slash commands in Antigravity.
- The hooks file shape (`.agents/hooks.json`) mirrors Claude Code's grouping with
  `matcher` and `hooks` arrays; verify it against your Antigravity version.
