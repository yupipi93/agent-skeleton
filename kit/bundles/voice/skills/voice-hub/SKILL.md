---
name: voice-hub
description: "The local voice hub where voice notes go by default: history and web player (tools/voice-hub, http://127.0.0.1:7473). Use when a voice note prints a hub link (paste it), the user asks what an agent said earlier, voice-note.py says the hub is down, or to run, check or fix the hub and its MCP server."
---

# Voice hub

The hub is the voice bundle's default channel (`NOTIFY_CHANNELS=hub`): every note sent by
`kit/bundles/voice/scripts/voice-note.py` is stored in the local hub (`tools/voice-hub`):
audio, transcript, the text you wrote, which agent and session sent it, the repo, and
whether the user has heard it. The user plays it at 1x to 2.5x with a follow-along
transcript, on this machine or (optionally) a phone over Tailscale. Telegram and Google
Chat are extra channels the user opts into; the hub stays on unless `VOICE_HUB=off`.

After storing a note, `voice-note.py` makes it heard (`VOICE_HUB_OPEN`): `auto` (default)
hands it to a hub tab that is already open (`avh play`), else opens the player link in the
default browser; `always` opens the browser; `never` only prints the link.

## After sending a voice note: paste the link

`voice-note.py` prints, on stdout:

```text
🎧 Voice hub: http://127.0.0.1:7473/n/<id>?play=1
Markdown: [🎧 Listen: <title>](http://127.0.0.1:7473/n/<id>?play=1)
```

**Copy the `Markdown:` line into your written reply.** A click plays the note (an open hub
tab takes it over). Optional flags that make the entry better: `--summary "<one line>"`,
`--link <url>` (PR, ticket, dashboard; URLs are never spoken), and, when the user has
something to do, `--brief "<one or two sentences>"` and `--command "<cmd>"` (shown first
with a copy button). A command sent with `notify.sh --code` in the same session is attached
too. The command still goes into your reply as a fenced block.

## Looking notes up

When the user asks "what did the agent say yesterday about the migration?", read the
text instead of asking them to listen:

```bash
tools/voice-hub/bin/avh list -q "migration" --json
tools/voice-hub/bin/avh show <id> --json
tools/voice-hub/bin/avh url last
```

If the MCP server is registered (`[mcp.voice-hub]` in `skeleton.local.toml`, see
`tools/voice-hub/README.md`), use its tools: `voice_notes_recent`, `voice_note_get`,
`voice_note_play` (an inline player in clients with MCP Apps), `voice_note_mark_heard`.

## Running it

```bash
tools/voice-hub/bin/avh serve                       # foreground
tools/voice-hub/bin/avh service install             # macOS login service
tools/voice-hub/bin/avh service install --tailnet   # also on your tailnet, for a phone
tools/voice-hub/bin/avh ping                        # is the server up? (exit 0 yes)
tools/voice-hub/bin/avh doctor                      # health, one line per dependency
```

Data lives in `~/.local/share/agent-skeleton/voice-hub/` (0700), never in git.

## When something fails

| Symptom | Fix |
|---|---|
| "the voice hub is not running" | Give the user the printed command (`avh service install` on macOS, `avh serve` elsewhere); `avh ping` checks it |
| No `🎧` lines after a note | `VOICE_HUB` is off, `--to` left the hub out, or the hub CLI failed. `avh doctor` |
| A browser tab opens for every note | Keep one hub tab open (it takes the next notes), or `VOICE_HUB_OPEN=never` |
| The link does not open | The server is down: `avh service status`, `avh service restart`, or `avh serve` |
| Phone link times out | Tailscale off on the phone, or this machine is asleep |
| "Re-record" fails | TTS credentials (skill `voice-summary`, engines) |

Never start a second server on the same port, and never kill hub processes by pattern;
use `avh service restart`.
