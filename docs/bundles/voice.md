# 🎧 voice

Off by default. Long, complex or decision-shaped turns end with a **spoken summary** you
can play away from the desk: a Telegram voice bubble with a speed control, a playable clip
in Google Chat, and (optionally) a local hub with history, a 1x to 2.5x player and a
follow-along transcript. Text notifications, with the "a command goes to both places" rule,
come in the same bundle.

```bash
bin/skeleton enable voice      # skills, rule and Stop hook
bin/skeleton setup voice       # the wizard: channels, voice, language, hub
```

## Skills

| Skill | Use it for |
|---|---|
| `voice-summary` | When to send a voice note, how to write for the ear, flags, exit codes |
| `notify` | Text notifications, levels, `--code-only`, the both-places rule for commands |
| `voice-hub` | Pasting the hub link, looking past notes up, running the hub |

## Rule (always on)

| Rule | In short |
|---|---|
| `notify-on-long-tasks` | 4+ minutes, 15+ tool calls, a subagent, a decision or a 1200+ character reply: send a voice note. "no audio" skips one turn |

## Hook

| Hook | Event | Tools | What it does |
|---|---|---|---|
| `voice-summary-stop` | `stop` | Claude Code (`Stop`), Cursor (`stop`), Gemini CLI (`AfterAgent`, ms timeout), Antigravity (`Stop`) | Blocks the end of a qualifying turn until a voice note was **delivered**; inert with no channel; gives up after 3 blocks |

The hook reads the turn from the transcript (Claude Code and Cursor JSONL, Gemini chat
JSON), counts tool calls, subagents, `notify.sh --code` sends, questions, minutes and reply
length, and accepts a `voice-note.py` call only if the voice log shows a `sent note` line
written during the turn. Claude Code, Gemini CLI and Antigravity get exit 2 with the
reason; Cursor gets `{"followup_message": ...}`. Turn it off with
`[hooks] voice-summary-stop = false` in `skeleton.local.toml`.

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/voice/scripts/voice-note.py` | Speak a summary (Google Chirp 3 HD, macOS `say`, or text) and deliver it; `--dry-run`, `--plan`, `--self-test` |
| `kit/bundles/voice/scripts/voice-note-hook.py` | The Stop hook (`--client claude\|cursor\|gemini\|antigravity`) |
| `kit/bundles/voice/scripts/notify.sh` | Text notifications: levels, `--code`, `--code-only`, `--dry-run`, `--test` |
| `kit/bundles/voice/scripts/notify-setup.sh` | The setup wizard (also `bin/skeleton setup voice`); `--show` lists the keys set |
| `kit/bundles/voice/scripts/tts-set-api-key.sh` | Validate and store a Google TTS API key (hidden prompt, header auth) |
| `kit/bundles/voice/scripts/lib/notifylib.py` | Shared config parser, channels and senders |
| `tools/voice-hub/bin/avh` | The optional hub: [tools/voice-hub/README.md](../../tools/voice-hub/README.md) |

## Ten-minute setup

1. **Dependencies** (1 to 3 minutes): `brew install ffmpeg` (in the Brewfile's `voice`
   group; `bin/install-mac.sh` installs it once the bundle is on).
2. **A Telegram bot** (2 minutes): in Telegram, talk to **@BotFather**, send `/newbot`,
   pick a name, copy the token.
3. **The wizard** (2 minutes): `bin/skeleton enable voice && bin/skeleton setup voice`.
   Paste the token at the hidden prompt, press START on your bot and send it any message
   (that is how the chat id is discovered), skip or add Google Chat, keep the free macOS
   voice, choose `en` or `es`, your first name for the greeting, and whether to keep a
   local hub. Say yes to the test at the end.
4. **Optional, Google voices** (5 minutes): in a Google Cloud project, enable the Cloud
   Text-to-Speech API, create an API key restricted to `texttospeech.googleapis.com`, run
   `kit/bundles/voice/scripts/tts-set-api-key.sh`. Chirp 3 HD voices sound far more natural;
   the free tier covers about one million characters a month (a five-minute note is about
   4500).
5. **Optional, Google Chat:** a space's *Apps & integrations > Webhooks* URL gives text and
   a "Listen" card. Audio in Chat also needs `GCHAT_SPACE` and the `google` bundle's
   `gchat.py login` (a 20-minute OAuth client setup, see [google](google.md)).
6. **Optional, the hub:** `tools/voice-hub/bin/avh service install` (macOS login service),
   then the `voice-hub` skill. Add `--tailnet` to reach it from a phone.

## Configuration: `~/.config/agent-skeleton/notify.env`

KEY=VALUE, mode 0600, written by the wizard; every key can also be an environment variable.

| Key | Default | Meaning |
|---|---|---|
| `NOTIFY_CHANNELS` | `auto` | `telegram`, `chat`, a comma list, `none`, or `auto` (every configured one) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | From @BotFather and the wizard |
| `GCHAT_WEBHOOK_URL` | empty | Incoming webhook: text and cards, no OAuth (a secret) |
| `GCHAT_SPACE` | empty | `spaces/...`: audio upload through `gchat.py` (google bundle) |
| `GCHAT_PING_USER` | empty | `users/<id>` mentioned in the first webhook message |
| `TTS_ENGINE` | `auto` | `google`, `say`, `none`; auto picks google with a key or account, else say, else none |
| `TTS_API_KEY` | empty | Google TTS key, sent in the `X-Goog-Api-Key` header |
| `TTS_GCLOUD_ACCOUNT`, `TTS_QUOTA_PROJECT` | empty | Use a gcloud user token instead of a key (`x-goog-user-project`) |
| `TTS_LANG` | `[user] language`, else `en` | `en` or `es` |
| `TTS_VOICE` | engine default | A Chirp voice (`en-US-Chirp3-HD-Charon`) or a `say -v` name |
| `TTS_SPEED` | `1.0` | Speed of the channel copies (the hub keeps the natural-rate recording) |
| `VOICE_GREETING` | `Hi` / `Hola` | First word of the note |
| `VOICE_USER_NAME` | `[user] name` | Appended to the greeting |
| `VOICE_SPEAKERS_FILE` | `~/.config/agent-skeleton/speakers.json` | Repo folder to spoken name, see below |
| `VOICE_HUB`, `VOICE_HUB_CLI` | `off`, `tools/voice-hub/bin/avh` | Store every note in the local hub |
| `NOTIFY_TZ` | system | Time zone of the notification footer |
| `VOICE_HOOK_LONG_SECONDS`, `VOICE_HOOK_TOOL_CALLS`, `VOICE_HOOK_REPLY_CHARS` | `240`, `15`, `1200` | Stop hook thresholds (`0` disables one) |
| `VOICE_HOOK_OPTOUT` | `no audio` | Phrase(s), comma separated, that skip the hook for one turn |

`speakers.json` names repositories out loud when "the payments api agent" is not good
enough:

```json
{ "payments-api": { "en": "the payments agent", "es": "el agente de pagos", "tag": "payments" },
  "infra-live": "the infrastructure agent" }
```

Logs: `~/.local/state/agent-skeleton/voice.log` and `notify.log` (0600, no secrets).
`--dry-run` audio goes to `~/.local/state/agent-skeleton/dry-run/`.

## How a note is built

1. The text is made speakable: markdown, emoji, URLs and code blocks are stripped; a fenced
   block becomes "The command is in the chat."
2. The opening sentence is added by the script, never by the caller: "Hi, Ana. This is the
   payments agent, about Terraform." (in Spanish it opens with "Hola" and continues "Soy el
   agente de pagos, sobre Terraform."), from the git repository you stand in and `--source`.
3. Synthesis: Google splits long text at paragraph and sentence boundaries under the
   5000-byte request limit, synthesises PCM and encodes one Opus clip; `say` has no limit.
4. Delivery: each channel is tried independently; the text fallback runs only when the
   audio itself failed. Exit 0 all good, 3 partial (do not resend), 1 nothing delivered.

## Security notes

- Secrets live only in `notify.env` (0600, directory 0700); scripts warn when it is looser.
- Python sends every request in-process (no secret on a command line); the shell wizard
  passes the Telegram token and the TTS key to curl through `curl -K -` on stdin, and stores
  them with `envfile.py set` on stdin.
- Error messages are scrubbed of the bot token, the webhook URL and the API key.
- Nothing is sent without an explicit call; `--dry-run` and `--plan` never send.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "no channel configured" | `bin/skeleton setup voice`, or `notify-setup.sh --show` to see what is set |
| The note arrives as text | The engine failed: read stderr; Google key (`tts-set-api-key.sh`), gcloud login, or `brew install ffmpeg` for `say` |
| Telegram hangs or times out | The network blocks `api.telegram.org` (some managed networks and security tools do); use Google Chat |
| Chat shows the caption but no audio | No `GCHAT_SPACE`, or `gchat.py login` missing; the webhook alone cannot upload files |
| The hook blocks a turn that sent a note | The send failed: check `voice.log` for `sent note`; after 3 blocks the turn ends anyway |
| The hook never fires | No channel configured (it is inert), or `[hooks] voice-summary-stop = false` |

## Dependencies

`python3`, `curl`, `ffmpeg` (Homebrew `ffmpeg`, with libopus; libx264 for the Chat
waveform clip). Optional: `say` (macOS), `gcloud`.
