# Decisions

Short records of choices made where the design contract left room. Newest last.

## D1. One CLI file, stdlib only

`bin/skeleton` is a single Python file (frontmatter parser, TOML writer, renderers,
commands). No package, no install step, no PyYAML. Tests load it with `importlib`.

## D2. Re-exec on old Python

macOS ships `python3` 3.9. `bin/skeleton` keeps its top section parseable by old
interpreters and re-executes itself with the newest `python3.X` (>= 3.11) found on `PATH`
or in the Homebrew prefixes. The rest of the file avoids 3.10+ syntax (`match`) for the
same reason. Shared bundle scripts (`envfile.py`, `secretscan.py`) target Python 3.8+.

## D3. Generated-path manifest and ownership

`init` records every path it generated in `.skeleton/generated.json`. Pruning removes
what the previous run generated and this run did not. A pre-existing file that the
generator did not create is skipped with a warning (exit 1) unless `--force`; this
protects a user's own `.claude/settings.json`. Owned directories (`.claude/skills`,
`.agents/rules`, ...) are also swept for links into the kit and marker-carrying files, so
a lost manifest does not leave stale entries.

## D4. Writes only on change

Files are rewritten only when their content changes and links only when their target
changes. Two consecutive `init` runs leave the tree identical, timestamps included, which
is what the idempotency test asserts.

## D5. `--tools` is a one-off override

`init --tools claude` renders only those tools and prunes the others. It is not
persisted; set `tools` in `skeleton.local.toml` to make it permanent (otherwise `doctor`
reports the tree as stale).

## D6. Precedence of toggles

`default_enabled` < `skeleton.toml` < `skeleton.local.toml` for bundles. For skills,
rules and hooks an explicit entry beats the bundle state, so one skill can be enabled
from a disabled bundle. Local bundles default to on.

## D7. `enable` / `disable` minimise the local file

When a toggle returns a key to its default value, the writer removes the key (and an
empty table it leaves behind) instead of writing `= true`. A `disable` then `enable` round
trip leaves `skeleton.local.toml` byte-identical. Bare TOML keys are written when valid
(`plan-files = false`), quoted otherwise.

## D8. Invocation values

`[skills] "<s>" = { invocation = "user" | "model" | "auto" }`: `user` sets
`disable-model-invocation: true`, `model` sets `user-invocable: false`, `auto` removes
both. Applied to a rendered copy in `.skeleton/rendered-skills/<s>/` whose other entries
are links to the source, so `references/` and `scripts/` keep working.

## D9. Overrides replace, they do not add

`[overrides]` only replaces an existing kit skill. New private skills belong in
`local/bundles/<b>/skills/`, which keeps one discovery mechanism.

## D10. Belt and braces for disabled skills

Disabled skills are not linked, and are also written as `"off"` in Claude Code
`skillOverrides` and in Gemini CLI `skills.disabled`, so a copy reaching the tool through
a user-level folder or plugin is also silenced.

## D11. Rule renderings

- Claude: `paths:` as a block list of double-quoted globs; always rules have no
  frontmatter; manual rules are not rendered.
- Cursor and Antigravity: `globs` as an unquoted comma string (`**/*.tf,**/*.tfvars`),
  the format both tools document; `description` double-quoted.
- Gemini: one `.gemini/RULES.md`, always rules first, then a "Scoped rules" section with
  an "Applies to files matching" line per rule; manual rules omitted.
- Every rendered rule carries an HTML comment naming its source file.

## D12. Optional user profile rule

`[user] name` and a non-English `language` produce a generated rule
`skeleton-user-profile` (name, reply language). `AGENTS.md` stays a static committed file.

## D13. Hook rendering details

- Each hook becomes its own matcher group (Claude, Gemini, Antigravity) or entry (Cursor).
- Cursor MCP and shell hooks use `beforeMCPExecution` / `beforeShellExecution` without a
  `matcher`; scripts filter by server or command themselves.
- Antigravity shell matches get no matcher (its tool names are not documented); scripts
  filter.
- Antigravity has no `prompt_submit` or `session_end` mapping; those hooks are skipped.
- Command prefixes: `"$CLAUDE_PROJECT_DIR"/`, `"$GEMINI_PROJECT_DIR"/`, `./`.
- Hooks with no rendered entries leave no file (`.cursor/hooks.json`,
  `.agents/hooks.json` appear only when needed); same for MCP files.

## D14. MCP values

`${VAR}` is passed through (Cursor: `${env:VAR}`, defaults dropped). `${SKELETON_ROOT}`
expands to the absolute checkout path, and a leading `~/` in `command` is expanded,
because generated files are machine-local anyway. Remote servers: Claude `type` +
`url`, Cursor `url`, Gemini `httpUrl` (or `url` for `type = "sse"`), Antigravity
`serverUrl`. `[mcp.<name>]` in the local file can also declare a new server.

## D15. Text guard

- Patterns live in `kit/bundles/core/scripts/lib/secret-patterns.txt` as
  `<label> <POSIX ERE>`, shared by `text-guard.sh` and `secretscan.py` (which maps POSIX
  classes to Python). The guard reports the label, never the matched text.
- Exit 2 blocks (all four tools treat exit 2 as a block). On allow, `--client cursor`
  prints `{"permission":"allow"}` and `--client gemini` `{"decision":"allow"}`; Claude and
  Antigravity get no output.
- A missing pattern file blocks (fail closed).
- The em dash check is opt-in (`--em-dash`) because the style bundle is off by default.
  The byte sequence is built with `printf` octal escapes, so no script contains the
  character.

## D16. `check` scope

Structural checks run on every bundle, kit and local. Text checks (em dash, denylist)
run only on tracked kit content (kit, docs, bin, tests, root files): private bundles are
the user's business. The denylist holds generic shapes only (home paths, real-looking
emails); its patterns are written so the file does not match itself.

## D17. Brewfile groups

`# group: <bundle>` comment markers group the Brewfile. `install-mac.sh` installs core
plus the groups of enabled bundles (via `bin/skeleton list --names --enabled`); when no
Python >= 3.11 exists yet, it installs `core` first (which brings `python@3.12`), then the
rest. `--groups` and `--all` override. `ripgrep` is in core (agents and the allowlist use
`rg`); `shellcheck` is in a `dev` group for contributors. Commented entries count as
documented for `check`'s bundle-to-Brewfile cross-check.

## D18. Claude permission syntax

The template uses the space-wildcard form (`Bash(git log *)`) with explicit bare forms
where a command is often run without arguments (`Bash(terraform apply)`). Denies cover
apply/destroy, force pushes, hard resets, common `rm -rf` spellings, `pkill`, `killall`
and project create/delete. Deny lists are a speed bump, not a sandbox; the rules carry
the real policy.

## D19. Plans are git-ignored

`plans/` is ignored so personal plans never reach the public repository. Remove the line
from `.gitignore` in a fork that should version them.

## D20. Bundle manifest extras

Beyond the contract fields, `bundle.toml` accepts `version`, `commands` (executables
`doctor` requires) and `optional_commands` (reported as info), because Homebrew names
rarely equal command names (`google-cloud-sdk` provides `gcloud`).

## D21. `notify.sh` is a thin wrapper over `notifylib.py`

`kit/bundles/voice/scripts/notify.sh` only checks for `python3` and `exec`s
`lib/notifylib.py notify "$@"`. Config parsing, channel resolution, HTML conversion and
every HTTP request live in that one Python module, shared with `voice-note.py`, so the bot
token, the webhook URL and the TTS key stay inside one process: never on a command line,
never in a log, and there is one place to scrub them from error messages.

## D22. `NOTIFY_CHANNELS=auto` by default

Superseded by D35. It used every configured channel (Telegram when it had a token and a
chat id, Google Chat when it had a webhook or a space). `auto` now means the local voice
hub only.

## D23. `voice-note.py --dry-run` versus `--plan`

`--plan` prints the spoken text only (no synthesis, no network, instant): it is how an
agent or a test checks what will be said. `--dry-run` runs the whole pipeline locally
(speakable text, synthesis, encoding) and writes the audio under
`~/.local/state/agent-skeleton/dry-run/`, but sends nothing. Neither counts as a send for
the Stop hook.

## D24. Voice exit 3 means "partial, do not resend"

`voice-note.py` exits 0 when every channel got the note, 1 when nothing was delivered (or
nothing is configured), 2 on bad usage, and 3 when the note reached at least one channel but
another failed, or the audio failed and the text fallback went out. Exit 3 tells the agent
the user already has the summary, so it must not send it again. `notify.sh` uses the same
0 / 3 / 1 codes, except that with `NOTIFY_CHANNELS=none` (or an opted-in channel without
credentials) it is a silent no-op that exits 0, so an emitter never breaks because a token
is missing.

## D25. The Stop hook counts a note only from the voice log

`voice-note-hook.py` does not trust the transcript alone: a `voice-note.py` call in the
turn counts only when `~/.local/state/agent-skeleton/voice.log` has a `sent note` line
written during that turn. Dry runs, plans, self-tests and failed sends do not satisfy it.
After three blocks in a row the turn is allowed to end anyway, so a broken channel never
traps a session.

## D26. `TELEGRAM_API_BASE` is a test-only override

`notifylib.py` reads `TELEGRAM_API_BASE` (default `https://api.telegram.org`) from the
environment only, never from `notify.env`, so tests can point it at a local fake server on
127.0.0.1. It is not documented as a user setting.

## D27. The voice-hub MCP server is opt-in

The voice bundle ships no `mcp.toml`: the hub's MCP server needs a machine path and only
makes sense when the hub runs. Users who want it declare it in `skeleton.local.toml`:

```toml
[mcp.voice-hub]
command = "python3"
args = ["${SKELETON_ROOT}/tools/voice-hub/bin/avh", "mcp"]
```

## D28. `GIT_HOST` is optional

The PR host is read from the origin URL (`github.com` or `bitbucket.org`). `GIT_HOST`
(`github` or `bitbucket`) only overrides it, for mirrors and custom hostnames, so the common
case needs no setting.

## D29. Jira board configs are private data

Per-board settings (project key, issue and request types, title format, transitions,
assignee and reporter, public comments) are TOML files read by the agent, looked up in
`local/bundles/*/jira-boards/<KEY>.toml` (a private bundle, versionable in a private repo)
and then `~/.config/agent-skeleton/jira-boards/<KEY>.toml`. The kit ships only
`board.example.toml`. Scripts take flags, not board files, so they stay simple.

## D30. `jira-mcp-guard.sh` wraps the text guard for MCP calls

The `before_tool` hook for Atlassian or Jira MCP servers is a small wrapper, not the text
guard itself: Cursor's `beforeMCPExecution` fires for every server, so the wrapper filters by
tool and server name, decodes the JSON payload so an escaped secret cannot slip past, and
then runs `core/scripts/text-guard.sh` on the result. Other MCP calls pass untouched.

## D31. JSON helpers instead of `jq`

The Jira scripts parse and build JSON with small, unit-tested Python helpers
(`kit/bundles/jira/scripts/lib/jira_json.py`, `lib/adf.py`), and the git PR scripts with
short inline `python3` snippets, instead of `jq`, so they run on a stock Mac and their logic
is testable offline. `jq` stays in the core Brewfile group as an
optional convenience for humans; no kit script needs it.

## D32. Billing report config: TOML or JSON, YAML only with PyYAML

`tools/billing-exec-report` reads TOML (Python 3.11+ `tomllib`) or JSON with the standard
library. A `.yaml` config works only when PyYAML happens to be installed, and the tool says
so clearly otherwise. Nothing in the kit depends on PyYAML.

## D33. Small helper scripts for gcp and docs

Recipes that were long shell snippets in skills became scripts with tests:
`kit/bundles/gcp/scripts/gcp-account.py` (project id to gcloud account from a glob map,
read-only, never switches the active account), `kit/bundles/docs/scripts/chrome.sh`
(find Chrome on macOS or Linux, print to PDF or screenshot with a throwaway profile) and
`kit/bundles/docs/scripts/open-local.sh` (open a local file with the platform opener).

## D34. CI on macOS and Linux

`.github/workflows/ci.yml` runs `bin/skeleton check` and `bin/skeleton test` on
`macos-latest` and `ubuntu-latest` with Python 3.12. Tests that need macOS-only tools
(`say`) or optional binaries (`ffmpeg` with libopus, Chrome) skip themselves when the tool
is missing; everything else, including the bash 3.2 syntax checks, runs on both.

## D35. Voice notes go to the local hub by default; Telegram and Chat are opt-in

`NOTIFY_CHANNELS` defaults to `hub` and `VOICE_HUB` to `on`: a voice note is stored in the
local voice hub (`tools/voice-hub`, loopback only) and played, in a hub tab that is already
open (`avh play`, built on the server's existing play hand-off) or else by opening the
`?play=1` link in the default browser (`VOICE_HUB_OPEN=auto|always|never`, opener
overridable with `VOICE_HUB_OPENER`). `auto` means `hub`. Telegram and Google Chat keep
their full code and tests but are used only when listed (`NOTIFY_CHANNELS=hub,telegram`)
or passed with `--to`; credentials alone never turn them on. Reasons: a summary of work in
progress is work content and should not leave the machine unless the user decides so; a
web player gives speed control, history and a transcript that chat apps do not; and some
managed networks block the external APIs outright.

Consequences. If the hub is the only channel and its server is down, `voice-note.py`
prints one line with the command that starts it (`avh service install` on macOS, `avh
serve` elsewhere) and exits 1; it never falls back to an external channel on its own. With
an external channel opted in as well, the missing hub makes the result partial (exit 3).
`notify.sh` on the hub channel prints the message locally and attaches any command to the
session's hub note, since the hub keeps voice notes, not text. The Stop hook stays inert
until `notify.env` exists, so enabling the bundle never blocks a turn before setup has run.
The setup wizard installs the hub first and offers the external channels as an advanced,
optional step.
