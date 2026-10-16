# Research notes

The question: how close to the agent's own chat can a spoken summary be played, and
what does each surface actually render? Findings below drove every design choice.
"Verified" means checked against the cited source; "inferred" means reasoned, not
confirmed.

## 1. Inline audio in agent chats

| Client | Inline player possible? | What works |
|---|---|---|
| Cursor Agent chat | **Yes, via MCP Apps** (Cursor 2.6+, gradual per-account rollout, regressed in 3.9.16-3.11.x, fixed 3.12) | `voice_note_play` MCP tool with a `ui://` resource |
| Claude Code CLI | No (terminal) | Clickable `http://127.0.0.1` link |
| Claude Code extension in Cursor/VS Code | No: MCP Apps unsupported (anthropics/claude-code#95149, #88881), markdown images render as `[Image]`, raw HTML is escaped, `vscode://`/`cursor://` hrefs are blanked (#76505) | `http(s)` links stay clickable |
| Cursor CLI | No (terminal) | Link |
| VS Code Copilot | Yes, MCP Apps since 1.109 | Same MCP tool |

- MCP Apps: extension `io.modelcontextprotocol/ui`, stable 2026-01-26. Tool declares
  `_meta.ui.resourceUri`; resource MIME `text/html;profile=mcp-app`; the View talks to
  the host with JSON-RPC over `postMessage` (`ui/initialize`,
  `ui/notifications/initialized`, `ui/notifications/tool-result`, `tools/call`,
  `ui/open-link`, `ui/notifications/size-changed`). Default CSP allows
  `media-src 'self' data:`, so the player loads the audio as a `data:` URL through an
  app-only tool rather than relying on the host honouring `resourceDomains` for
  `http://127.0.0.1`. Sources: the spec at
  github.com/modelcontextprotocol/ext-apps (specification/2026-01-26/apps.mdx),
  cursor.com/changelog/2-6, code.visualstudio.com/updates/v1_109.
- Cursor opens localhost links in its built-in browser tab
  (`workbench.browser.openLocalhostLinks`), so a hub link from either chat can open
  inside the editor.
- **Codec trap:** VS Code's Chromium build has no AAC or Opus decoder
  (microsoft/vscode#310736, #180780). MP3 is the only format confirmed in Chrome,
  Safari and VS Code webviews. Hence MP3 storage.

## 2. Agent identity from the shell

| Agent | Variables (checked in this order) |
|---|---|
| Claude Code | `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT` (`cli`, `claude-vscode`, `sdk-*`, `claude-desktop`, `remote_*`), `CLAUDE_CODE_SESSION_ID`; inside Cursor it also inherits `CURSOR_*`, so Claude is checked first |
| Gemini CLI | `GEMINI_CLI=1` (documented) |
| Antigravity | `ANTIGRAVITY_AGENT` (unofficial) |
| Codex | `CODEX_THREAD_ID`, `CODEX_SANDBOX` (unofficial) |
| Cursor CLI | `CURSOR_AGENT=1` |
| Cursor IDE agent | `CURSOR_TRACE_ID`, `CURSOR_EXTENSION_HOST_ROLE=agent-exec` |
| Fallback | `AI_AGENT` (Vercel proposal), then process ancestry via `ps` |

## 3. Hooks

- Claude Code `Stop`: `decision: "block"` + `reason` continues the turn;
  `systemMessage` shows a line to the user. Fires the same in CLI and IDE extensions.
- Cursor `hooks.json` `stop`: input `status`, `loop_count`; output `followup_message`
  (re-prompts the agent, not a display channel). Cursor also imports Claude Code hooks
  from `.claude/settings*.json` by default (Settings > Agents > Third-Party Imports),
  so a Claude `Stop` hook can fire for Cursor's own agent too.

## 4. Google Chat

- No API for voice messages; attachments are `UPLOADED_CONTENT` or `DRIVE_FILE` only.
  No playback-speed control on voice or video attachments. The waveform MP4 that
  `voice-note.py` already sends is the best inline Chat playback available.
- `cardsV2` needs app auth. Incoming webhooks can post cards with `openLink` buttons
  (widely used in practice, not stated on Google's webhook page). User-auth messages
  with an attachment cannot carry cards or accessory widgets.
- `markupSyntax: MARKUP_SYNTAX_MARKDOWN` is GA (2026-08-07) for user-auth messages.
- Chat cannot unfurl or render images from a tailnet host (Google fetches them).
- Decision: the webhook caption becomes a card with a "▶ Listen" button (hub URL) and
  a text fallback; the inline MP4 stays as the zero-tap option.

## 5. Mobile web audio

- `playbackRate` is reset to `defaultPlaybackRate` when `src` changes: set both.
- Chrome needs `Accept-Ranges` and 206 answers to seek; Safari probes `bytes=0-1`.
- The Cache API refuses 206 responses: cache the whole file, slice for range requests
  in the service worker.
- Media Session: Chrome shows lock-screen controls for media of 5 s or more;
  `setPositionState` throws on NaN duration or zero rate.
- Autoplay from a link tapped in another app is blocked: the page prepares the note
  and shows one big play button.
- Some Android vendors kill background apps aggressively: the browser and Tailscale
  may need *Unrestricted* battery usage (see dontkillmyapp.com for your vendor).
- Tailscale Serve: `tailscale serve --bg --https=8443 http://127.0.0.1:PORT` coexists
  with other Serve handlers (443 included), persists across reboots, and adds
  `Tailscale-User-Login` to proxied requests.
