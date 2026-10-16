---
name: voice-hub
description: "Optional local history and player for voice notes (tools/voice-hub, http://127.0.0.1:7473). Use when a voice note prints a hub link (paste it), when the user asks what an agent said earlier or for past audio summaries, or to start, check or fix the hub and its MCP server."
---

# Voice hub

With `VOICE_HUB=on` in `~/.config/agent-skeleton/notify.env`, every note sent by
`kit/bundles/voice/scripts/voice-note.py` is also stored in the local hub
(`tools/voice-hub`): audio, transcript, the text you wrote, which agent and session sent
it, the repo, and whether the user has heard it. The user plays it at 1x to 2.5x with a
follow-along transcript, on this machine or (optionally) a phone over Tailscale.

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
tools/voice-hub/bin/avh doctor                      # health, one line per dependency
```

Data lives in `~/.local/share/agent-skeleton/voice-hub/` (0700), never in git.

## When something fails

| Symptom | Fix |
|---|---|
| No `🎧` lines after a note | `VOICE_HUB` is off, or the hub CLI failed; the note was still delivered. `avh doctor` |
| The link does not open | The server is down: `avh service status`, `avh service restart`, or `avh serve` |
| Phone link times out | Tailscale off on the phone, or this machine is asleep |
| "Re-record" fails | TTS credentials (skill `voice-summary`, engines) |

Never start a second server on the same port, and never kill hub processes by pattern;
use `avh service restart`.
