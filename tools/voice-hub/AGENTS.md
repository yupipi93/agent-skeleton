# Agent guide: tools/voice-hub

Read [README.md](README.md) first. This file is for agents changing the hub.

- **Standard library only** (Python 3.9+) plus `ffmpeg`. Do not add dependencies or a
  build step to the front end; `avh/web/` is served as is.
- **Audio is MP3**, never AAC/Opus: the Chromium inside VS Code and Cursor cannot decode
  those (docs/research.md section 1).
- **Data is never in git.** It lives in `~/.local/share/agent-skeleton/voice-hub/`
  (0700). Tests use a temporary directory and a free port; never start a server on the
  default port from a test, a user's running hub may own it.
- Run `python3 -m unittest discover -s tests` from this folder before committing; the
  kit's `bin/skeleton test` runs it too. UI changes: check the phone layout.
- UI strings, code, comments and docs are English. Never write the em dash character.
- Conventional Commits.

## Using the hub from an agent (any repo)

- A note sent with `kit/bundles/voice/scripts/voice-note.py` while `VOICE_HUB=on` is
  stored here automatically, and the script prints a `Markdown: [🎧 Listen: <title>](...)`
  line. Put that line in your reply.
- Look notes up with `tools/voice-hub/bin/avh list --json` /
  `tools/voice-hub/bin/avh show <id> --json`, or through the MCP tools
  (`voice_notes_recent`, `voice_note_get`, `voice_note_play`).
