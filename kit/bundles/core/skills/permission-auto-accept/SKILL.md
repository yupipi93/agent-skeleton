---
name: permission-auto-accept
description: Install, configure and audit AI Auto-Accept, the VS Code / Cursor extension whose hook answers Claude Code permission prompts for you, with a deny-list that keeps destructive and gated commands. Use for auto-accept, auto yes, fewer approval clicks, or reviewing what it approved.
---

# Permission auto-accept

AI Auto-Accept (extension `devcloudops.ai-auto-accept`, source
`github.com/DevCloudOps1/claude-auto-accept`) answers Yes to Claude Code permission
prompts, except those whose text matches its deny-list, which stay with you. Set up as
below, it removes the routine clicks and keeps every prompt that a safety gate or an
organisation's policy needs a human for.

## When to use

- The user wants fewer "Do you want to proceed?" clicks, an "auto yes", or asks how
  the auto-accept tool works.
- Installing it on a new machine, or after an editor update broke the hook.
- Auditing what it approved: `kit/bundles/core/scripts/auto-accept-audit.py`.

## How it works

Two independent paths:

| Path | Covers | Mechanism |
|---|---|---|
| Claude Code hook | Claude Code panel (every chat, background tabs included) and the `claude` CLI in any terminal, even with the editor closed | A `PermissionRequest` hook in `<config dir>/settings.json`. Claude Code runs it only when it is about to show a prompt; the hook prints `allow` or nothing |
| Terminal watcher | `claude`, `codex`, `gemini`, `q`, `aider` in an editor terminal | Shell integration streams the output; a recognised prompt gets the keys for option 1 / `y` |

The hook, step by step:

1. Claude Code decides to ask (Manual mode before most edits and commands, auto mode
   only when its classifier or a policy `ask` rule wants a human).
2. It runs the hook with the tool call as JSON on stdin.
3. The hook reads `state.json` next to it (editor global storage): off, or a deny-list
   regex matches the tool input, case-insensitive, means it prints nothing and you get
   the prompt as usual. Otherwise it prints `allow` and the call runs.
4. Each decision is appended to `decisions.jsonl` (status bar counter, **Show Log**).

Facts that follow from this:

- **The deny-list never adds a prompt.** It only stops the hook from answering one that
  Claude Code was going to show anyway, so broad patterns cost nothing in auto mode.
- `AskUserQuestion` and `ExitPlanMode` (Claude's own questions, plan approval) are
  always left to you.
- The regexes match the whole tool input: a Bash command and its description, a Write
  or Edit file content, a URL. Editing a doc that mentions `git push` while Claude asks
  about that edit keeps the prompt.
- It is a safety net, not a sandbox: a command phrased to miss every pattern is
  answered Yes.
- The hook is written into the config dir active when it was enabled (it honours
  `CLAUDE_CONFIG_DIR`). With several Claude config dirs, each needs its own entry; the
  audit script lists them.

## Where it fits

| Option | Clicks | What still reaches you |
|---|---|---|
| `permissions.allow` rules (`allow_add` under `[settings.claude.permissions]` in `skeleton.local.toml`) | none for listed commands | everything else |
| Auto mode | few | what the classifier or a policy `ask` rule escalates |
| Manual mode + auto-accept | few | deny-listed prompts only |
| `--dangerously-skip-permissions` | none | nothing; only for throwaway sandboxes |

Recommended: auto mode plus allow rules for routine reads; add auto-accept for Manual
mode sessions, and always with the deny-list below.

## Install

1. Install the extension in every editor CLI found on `PATH`:

   ```bash
   kit/bundles/core/scripts/auto-accept-install.sh            # or --editor cursor, --dry-run
   ```

   VS Code installs it from the Visual Studio Marketplace. Cursor, Windsurf and VSCodium
   use Open VSX, which does not list it, so the script downloads the Marketplace VSIX
   and installs that file. No editor CLI on `PATH`: Command Palette, "Shell Command:
   Install 'code' / 'cursor' command in PATH".
2. **Choose the deny-list before turning anything on.** With no `denyList` key the
   extension's built-in list applies (destructive commands only). For the kit gates as
   well, print the kit list and paste it into the **User** settings JSON (Command
   Palette, "Preferences: Open User Settings (JSON)"). Workspace settings are ignored on
   purpose.

   ```bash
   kit/bundles/core/scripts/auto-accept-audit.py --print-settings
   # with machine-specific patterns (see "Managed machines"):
   AUTO_ACCEPT_EXTRA_DENY=~/path/to/extra-deny.json kit/bundles/core/scripts/auto-accept-audit.py --print-settings
   ```

3. Command Palette, **AI Auto-Accept: Set Up Chat Auto-Approve**, pick **Recommended**.
   Only for Claude Code: set `"claudeAutoAccept.claudePanel": true` in User settings.
4. Start a new chat and check (next section).

## Verify

- Status bar shows `✓ Auto-Accept <n>`; **AI Auto-Accept: Show Log** lists
  `ACCEPT [Claude Code] "Bash: ..."` and `BLOCKED ... (deny-list: answer it yourself)`.
- `kit/bundles/core/scripts/auto-accept-audit.py`: which config dirs carry the hook, on /
  off, deny-list size, and the prompts it answered that the recommended list would have
  left to you. Exit 1 means a warning to act on.

## Recommendations

1. **An empty deny-list is a deliberate choice, not a default.**
   `"claudeAutoAccept.denyList": []` replaces the built-in list with nothing, so
   `terraform apply` and `rm -rf` are answered Yes. Leave the key out to keep the
   built-in list. The audit warns about `[]`; when the user chose it, report it and leave
   it alone.
2. **Use the kit list** (`assets/deny-list.json`): the extension's built-in patterns plus
   the kit gates (Terraform apply, import and state edits, `git push` and `rebase`, SQL
   and BigQuery mutations, `gcloud` deletes, IAM and identity switches, the Jira and PR
   scripts that send text, `pkill` / `killall`, `sudo`). A custom list replaces the
   built-in one, so start from this file.
3. **A Yes from the hook is not the user's approval.** Gates (`agent-safety-gates`) still
   need an explicit go in the conversation before the command is run; the deny-list is
   the backstop that keeps the click when an agent forgets.
4. **Managed machines.** When an organisation's policy forces prompts (managed `ask`
   rules), auto-answering them defeats a security control, the same thing rule
   `permission-prompt-hygiene` forbids an agent to do by disguising a command. Mirror
   those commands in an extra deny file and pass it with `AUTO_ACCEPT_EXTRA_DENY`. The
   legitimate way to lose those prompts is an exception from the organisation.
5. Leave the Copilot **Everything** level alone: it has no deny-list.
6. Run the audit after a busy week, and after every editor update.

## Turn off or remove

- Pause: click **Auto-Accept** in the status bar or run **AI Auto-Accept: Toggle**.
- Remove the Claude hook: **Set Up Chat Auto-Approve**, **Undo** (or set `claudePanel`
  to `false`), then uninstall the extension. Uninstalling first leaves a hook entry that
  points at a missing script: harmless (prompts come back), but delete it from
  `<config dir>/settings.json` under `hooks.PermissionRequest`.
- Run the audit: it should report no hook.

## Gotchas

| Symptom | Cause and fix |
|---|---|
| Prompts again after an editor update | The hook command embeds the editor's helper binary path; run Set Up again |
| Counter stays at 0 in auto mode | Auto mode rarely asks; nothing to answer |
| One config dir answered, another not | The hook was written to one dir only; enable it with `CLAUDE_CONFIG_DIR` pointing at the other, or copy the `PermissionRequest` entry |
| "Claude is requesting permission" notice for a background chat | Shown before the hook answers; ignore it |
| A prompt already on screen is not answered | Only prompts raised after turning it on are; answer that one yourself |
| A deny pattern is ignored by the audit | Python cannot compile a JS-only construct; the extension still applies it |
