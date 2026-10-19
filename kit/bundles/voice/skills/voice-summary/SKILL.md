---
name: voice-summary
description: "Send the user a spoken summary with kit/bundles/voice/scripts/voice-note.py (local voice hub by default; Telegram or Google Chat only if opted in). Use after long or complex tasks, when a decision or command is needed, when the Stop hook asks, or when asked for audio. Covers writing for the ear."
---

# Voice summaries

A long written answer is a wall the user may not climb, especially away from the desk.
Two minutes of audio can be played while doing something else. So the end of a long,
complex or decision-shaped turn is also told out loud.

```bash
kit/bundles/voice/scripts/voice-note.py --source TERRAFORM --title "Plan ready" \
  "The plan is clean: three new resources and no destroys. I need your go to apply it."
printf '%s' "$summary" | kit/bundles/voice/scripts/voice-note.py --title "Release" --file -
```

## When to send one

Send one, before finishing, when any of these holds (the defaults; the user can change
them with `VOICE_HOOK_*` in `~/.config/agent-skeleton/notify.env`):

- **Long:** the turn took 4 minutes or more.
- **Complex:** 15 tool calls or more, or work delegated to a subagent.
- **Decision:** you need something from the user: an approval, a command to run, a
  choice between options.
- **A wall:** the written reply is 1200 characters or more.
- **Asked:** the user asks for it ("in audio", "voice summary").

Not for one-line answers: a voice note for "done, 3 files" is noise. The thresholds are a
floor: when the work mattered (something irreversible, a production change), send one even
if the hook stays quiet.

The Stop hook `voice-summary-stop` enforces this in Claude Code, Cursor, Gemini CLI and
Antigravity. It is inert until the bundle is configured (`notify.env` exists), lets the
turn end after three refusals, and stands down for one turn when the user writes
**"no audio"** (`VOICE_HOOK_OPTOUT`). A call counts only when the voice log shows a
delivery; a note stored in the hub is a delivery.

## Where it goes

By default the note goes to the **local voice hub** (`tools/voice-hub`, skill
`voice-hub`) and nowhere else: it is stored, the player link is printed, and it is played
(`VOICE_HUB_OPEN=auto`: an open hub tab takes it, else the link opens in the browser;
`always` opens the browser; `never` only prints the link). Telegram and Google Chat are
used only when the user opted in (`NOTIFY_CHANNELS=hub,telegram`) or you pass `--to` because
the user asked for that channel. Never add `--to telegram` or `--to chat` on your own.

If the hub server is down the script prints one line with the command that starts it and
exits 1. Give the user that command; do not retry and do not switch channels.

## Writing for the ear

The script strips markdown, emoji, URLs and code blocks before speaking, but that is a
safety net. Write the text as speech:

- **Lead with the conclusion.** The listener may stop after fifteen seconds.
- **Narrate, do not enumerate.** Join lists into sentences.
- **One to four minutes.** Longer stops being a summary, unless the user asked for detail.
- **End with what you need**, plainly: the last sentence is the ask.
- **Never read commands, paths, hashes, ids, URLs or IP addresses aloud.** Say "the ticket",
  "the PR", "the command is in the chat". They belong in the written reply.

| Written for the eye | Spoken |
|---|---|
| `dev`: 3 added, 1 changed | "in dev, three new resources and one change" |
| `PROJ-123` moved to Done | "the ticket is closed" |
| `terraform apply -target=...` | "the command is in the chat" |

Do not write your own greeting or "this is the X agent": the script builds the opening
sentence ("Hi, Ana. This is the payments agent, about Terraform.") from the repository you
are in, `VOICE_USER_NAME`, and `--source`. A greeting you write anyway is dropped.

## Commands go to both places

Audio is additive. A command the user must run goes to the notification channel with
`kit/bundles/voice/scripts/notify.sh --code-only "<cmd>"` **and** into your reply as a
fenced block (skill `notify`). Also pass `--command "<cmd>"` (shown first in the hub note
with a copy button) and `--brief "<one or two sentences>"`.

## Flags

| Flag | Use |
|---|---|
| `--source TAG` | `AGENT` (default), `TERRAFORM`, `DEPLOY`, `GCP`, `DB`, `SECURITY`, `BILLING`, `DNS`, `JIRA`, `ACTION` |
| `--title T` | Caption shown with the audio |
| `--lang en\|es` | Default `TTS_LANG` (then `[user] language`, then `en`) |
| `--to hub,telegram,chat\|none` | Channels for this call (default `NOTIFY_CHANNELS`, `hub`); external ones only when the user asked |
| `--open auto\|always\|never` | How the hub note is played (default `VOICE_HUB_OPEN`, `auto`) |
| `--who`, `--tag`, `--greeting`, `--no-opener` | Override the introduction |
| `--summary`, `--link URL`, `--command CMD`, `--brief B` | Extra fields for the hub |
| `--file -` | Read the text from stdin |
| `--plan` | Print the spoken text only |
| `--dry-run` | Synthesise to a local file and print its path; nothing is sent |
| `--self-test` | Offline checks |

## After sending

- Exit 0: delivered. Exit 3: partial (some channel failed, or the audio failed and the
  text went out instead); **do not send it again**, report the failed part. Exit 1:
  nothing delivered (for example the hub is not running); say so in the reply, with the
  start command the script printed.
- If it prints `Markdown: [🎧 Listen: ...](http://127.0.0.1:7473/n/...)`, paste that line
  into your reply (skill `voice-hub`).
- Log: `~/.local/state/agent-skeleton/voice.log`.

## Engines and setup

`TTS_ENGINE=auto` uses Google Cloud TTS (Chirp 3 HD voices) when `TTS_API_KEY` or
`TTS_GCLOUD_ACCOUNT` is set, else the macOS `say` voice (free, offline). With no engine
the hub has nothing to store (it keeps audio); opted-in external channels get the text.
Setup: `bin/skeleton setup voice`; Google key: `kit/bundles/voice/scripts/tts-set-api-key.sh`.
Details and troubleshooting: `docs/bundles/voice.md`.
