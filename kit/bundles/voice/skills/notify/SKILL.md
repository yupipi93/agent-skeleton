---
name: notify
description: "Text notifications with kit/bundles/voice/scripts/notify.sh: printed locally and attached to the voice hub by default, Telegram or Google Chat only when opted in. End of a long task, an incident, a result, a command to run, a blocking decision. Also the both-places rule for commands."
---

# Text notifications

```bash
kit/bundles/voice/scripts/notify.sh --source TERRAFORM ok "Plan applied in dev" "3 added, 0 destroyed."
kit/bundles/voice/scripts/notify.sh --source ACTION warn "Apply needs your approval" \
  "The plan replaces the database instance." --code-only "terraform apply -target=module.db"
```

`notify.sh [--source TAG] [--code CMD | --code-only CMD] [--to CHANNELS] [--dry-run]
[--quiet] <info|ok|warn|crit> <title> <message...>`

Channels come from `~/.config/agent-skeleton/notify.env` (`NOTIFY_CHANNELS`, a comma list
of `hub`, `telegram`, `chat`, or `none`; default `hub`, and `auto` means `hub`):

- **`hub`** (default): the message is printed here, and a `--code` / `--code-only` command
  is attached to this agent session's note in the local voice hub, shown first with a
  copy button. The hub stores voice notes, not text, so pair the notification with a
  voice note when the user is away (skill `voice-summary`).
- **`telegram`, `chat`**: opt-in. Used only when listed (`NOTIFY_CHANNELS=hub,telegram`)
  and configured, or with `--to` when the user asked for that channel. Never add them on
  your own.

With `none` (or an opted-in channel missing its credentials) the script is a silent no-op
that exits 0: an emitter never breaks for a missing config. Exit 0 sent, 3 partial, 1
nothing delivered. Log: `~/.local/state/agent-skeleton/notify.log`.

The spoken half of this channel is the skill `voice-summary`. A long or complex turn gets
both: the audio carries the explanation, this carries the text and the command.

## The rule before every other one: a command goes to both places

Every command the user might run must be one-click copyable in **both** places: the
notification channel (`--code` or `--code-only`; with the hub, the copy button in the
note) **and** a fenced bash block in your chat reply. Never a sentence describing the command instead of the command. `notify.sh` prints
the ready-made fenced block on stderr whenever it sends a command, as a reminder.

- `--code-only CMD` sends the command as its own message right after the explanation: on
  a phone, "select all" then copies only the command. Use it when the command is the ask.
- `--code CMD` puts the block inside the same message, when it is a detail.

## Levels

| Level | Icon | Notifies | Use it for |
|---|---|---|---|
| `crit` | 🚨 | yes | something is broken or losing data right now |
| `warn` | ⚠️ | yes | needs the user today: an approval, a drift, a quota |
| `ok` | ✅ | silently | a task finished cleanly |
| `info` | ℹ️ | silently | progress, context, an FYI |

**Always pass `--source`**: `AGENT`, `TERRAFORM`, `DEPLOY`, `GCP`, `DB`, `SECURITY`,
`BILLING`, `DNS`, `JIRA`, `ACTION`. It becomes the header icon and tag.

## Format

Title and message may use inline HTML: `<b>`, `<i>`, `<u>`, `<s>`, `<code>`. Telegram gets
it as HTML (anything else is escaped, unclosed tags are closed); Google Chat gets the
equivalent markup (webhook: `*bold*`; user token: Markdown). Long bodies are truncated on a
line boundary. If Telegram rejects the formatting, the message is retried as plain text.

## Before sending text outside the machine

With Telegram or Google Chat opted in, notifications leave the machine. Do not put secrets, tokens, internal hostnames or
customer data in them; when in doubt run `kit/bundles/core/scripts/text-guard.sh --file
<draft>` first.

## Testing

```bash
kit/bundles/voice/scripts/notify.sh --dry-run --source GCP ok "T" "body"   # renders, sends nothing
kit/bundles/voice/scripts/notify.sh --dry-run --to hub,telegram,chat ok "T" "b"  # preview each channel
kit/bundles/voice/scripts/notify.sh --test                                 # showcase to the real channels
```
