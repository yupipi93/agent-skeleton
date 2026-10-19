# 🎧 voice

Off by default. Long, complex or decision-shaped turns end with a **spoken summary**. By
default it goes to the **local voice hub** (`tools/voice-hub`), a web player on your
machine with history, a 1x to 2.5x speed control and a follow-along transcript, and it
starts playing: in a hub tab you already have open, or in a new browser tab. Nothing leaves
the machine. Telegram (a voice bubble with a speed control) and Google Chat (a playable
clip) are still there, fully working, as an **opt-in**: they are used only when you list
them in `NOTIFY_CHANNELS`. Text notifications, with the "a command goes to both places"
rule, come in the same bundle.

```bash
bin/skeleton enable voice      # skills, rule and Stop hook
bin/skeleton setup voice       # the wizard: hub, voice, language; external channels optional
```

## Defaults

| Setting | Default | What it means |
|---|---|---|
| `NOTIFY_CHANNELS` | `hub` | Voice notes go to the local hub only; `auto` means the same |
| `VOICE_HUB` | `on` | The hub channel is available (`off` removes it from every list) |
| `VOICE_HUB_OPEN` | `auto` | Play in an open hub tab, else open the player in the browser |
| Telegram, Google Chat | off | Used only when listed, e.g. `NOTIFY_CHANNELS=hub,telegram`, or `--to` for one call |
| Stop hook | inert until `notify.env` exists | A new install is never blocked |

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
| `voice-summary-stop` | `stop` | Claude Code (`Stop`), Cursor (`stop`), Gemini CLI (`AfterAgent`, ms timeout), Antigravity (`Stop`) | Blocks the end of a qualifying turn until a voice note was **delivered** (the hub counts); inert until the bundle is configured; gives up after 3 blocks |

The hook reads the turn from the transcript (Claude Code and Cursor JSONL, Gemini chat
JSON), counts tool calls, subagents, `notify.sh --code` sends, questions, minutes and reply
length, and accepts a `voice-note.py` call only if the voice log shows a `sent note` line
written during the turn; a note stored in the hub is a delivery. It stays inert while
`~/.config/agent-skeleton/notify.env` does not exist, so enabling the bundle never blocks
anyone before `bin/skeleton setup voice` has run. Claude Code, Gemini CLI and Antigravity
get exit 2 with the reason; Cursor gets `{"followup_message": ...}`. Turn it off with
`[hooks] voice-summary-stop = false` in `skeleton.local.toml`.

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/voice/scripts/voice-note.py` | Speak a summary (Google Chirp 3 HD or macOS `say`), store it in the hub and play it; opted-in external channels too; `--dry-run`, `--plan`, `--self-test` |
| `kit/bundles/voice/scripts/voice-note-hook.py` | The Stop hook (`--client claude\|cursor\|gemini\|antigravity`) |
| `kit/bundles/voice/scripts/notify.sh` | Text notifications: printed locally with commands attached to the hub note, or sent to opted-in channels; `--code`, `--code-only`, `--dry-run`, `--test` |
| `kit/bundles/voice/scripts/notify-setup.sh` | The setup wizard (also `bin/skeleton setup voice`); `--show` lists the keys set |
| `kit/bundles/voice/scripts/tts-set-api-key.sh` | Validate and store a Google TTS API key (hidden prompt, header auth) |
| `kit/bundles/voice/scripts/lib/notifylib.py` | Shared config parser, channels and senders |
| `tools/voice-hub/bin/avh` | The hub, the default destination: [tools/voice-hub/README.md](../../tools/voice-hub/README.md) |

## Ten-minute setup

1. **Dependencies** (1 to 3 minutes): `brew install ffmpeg` (in the Brewfile's `voice`
   group; `bin/install-mac.sh` installs it once the bundle is on). The hub and both voices
   need it.
2. **The wizard** (3 minutes): `bin/skeleton enable voice && bin/skeleton setup voice`.
   - Say yes to installing the hub as a login service (macOS, `avh service install`; on
     Linux run `tools/voice-hub/bin/avh serve` under your own supervisor).
   - Keep the play mode `auto`, keep the free macOS voice (or give a Google key), choose
     `en` or `es` and your first name for the greeting.
   - Answer no to the advanced step (Telegram, Google Chat) unless you want notes to
     leave the machine.
   - Say yes to the test note: the player opens and speaks.
3. **Keep a hub tab open** (`tools/voice-hub/bin/avh open`): the next notes play there
   instead of opening a new tab each time.
4. **Optional, Google voices** (5 minutes): in a Google Cloud project, enable the Cloud
   Text-to-Speech API, create an API key restricted to `texttospeech.googleapis.com`, run
   `kit/bundles/voice/scripts/tts-set-api-key.sh`. Chirp 3 HD voices sound far more natural;
   the free tier covers about one million characters a month (a five-minute note is about
   4500).
5. **Optional, your phone:** `tools/voice-hub/bin/avh service install --tailnet` publishes
   the hub on your tailnet (see the [hub README](../../tools/voice-hub/README.md)).

### Advanced, optional: Telegram and Google Chat

Both stay in the bundle, fully working, and off. Run the wizard again and answer yes to the
advanced step, or edit `notify.env` yourself:

```bash
NOTIFY_CHANNELS=hub,telegram       # hub plus Telegram; hub,chat or hub,telegram,chat also work
```

- **Telegram:** in Telegram, talk to **@BotFather**, send `/newbot`, copy the token; the
  wizard validates it and discovers your chat id after you press START on your bot.
- **Google Chat:** a space's *Apps & integrations > Webhooks* URL gives text and a
  "Listen" card. Audio in Chat also needs `GCHAT_SPACE` and the `google` bundle's
  `gchat.py login` (a 20-minute OAuth client setup, see [google](google.md)).
- Listing only an external channel (`NOTIFY_CHANNELS=telegram`) skips the hub; `--to` sets
  the channels for one call. Credentials alone never turn a channel on.

## Configuration: `~/.config/agent-skeleton/notify.env`

KEY=VALUE, mode 0600, written by the wizard; every key can also be an environment variable.

| Key | Default | Meaning |
|---|---|---|
| `NOTIFY_CHANNELS` | `hub` | A comma list of `hub`, `telegram`, `chat`, or `none`. `auto` means `hub`; `all` means the hub plus every configured external channel |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | From @BotFather and the wizard |
| `GCHAT_WEBHOOK_URL` | empty | Incoming webhook: text and cards, no OAuth (a secret) |
| `GCHAT_SPACE` | empty | `spaces/...`: audio upload through `gchat.py` (google bundle) |
| `GCHAT_PING_USER` | empty | `users/<id>` mentioned in the first webhook message |
| `TTS_ENGINE` | `auto` | `google`, `say`, `none`; auto picks google with a key or account, else say, else none |
| `TTS_API_KEY` | empty | Google TTS key, sent in the `X-Goog-Api-Key` header |
| `TTS_GCLOUD_ACCOUNT`, `TTS_QUOTA_PROJECT` | empty | Use a gcloud user token instead of a key (`x-goog-user-project`) |
| `TTS_LANG` | `[user] language`, else `en` | `en` or `es` |
| `TTS_VOICE` | engine default | A Chirp voice (`en-US-Chirp3-HD-Charon`) or a `say -v` name |
| `TTS_SPEED` | `1.0` | Speed of the Telegram and Chat copies (the hub keeps the natural-rate recording) |
| `VOICE_GREETING` | `Hi` / `Hola` | First word of the note |
| `VOICE_USER_NAME` | `[user] name` | Appended to the greeting |
| `VOICE_SPEAKERS_FILE` | `~/.config/agent-skeleton/speakers.json` | Repo folder to spoken name, see below |
| `VOICE_HUB`, `VOICE_HUB_CLI` | `on`, `tools/voice-hub/bin/avh` | The hub channel (`off` removes it) and its CLI |
| `VOICE_HUB_OPEN` | `auto` | After storing: `auto` plays in an open hub tab, else opens the browser; `always` opens the browser; `never` prints the link only. `--open` per call |
| `VOICE_HUB_OPENER` | `open` (macOS), `xdg-open` (Linux) | Command that opens the player URL (split like a shell line, never run through a shell) |
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
4. Delivery: the hub is checked first (`avh ping`); if it is down the script prints one
   line with the command that starts it and exits 1, and never falls back to Telegram or
   Chat on its own. The note is stored (`avh add`), then played (`avh play` hands it to an
   open hub tab within 3 seconds; otherwise the `?play=1` link opens in the browser).
   Opted-in external channels are tried independently; the text fallback runs only when
   the audio itself failed. Exit 0 all good, 3 partial (do not resend), 1 nothing
   delivered.

## Security notes

- Secrets live only in `notify.env` (0600, directory 0700); scripts warn when it is looser.
- Python sends every request in-process (no secret on a command line); the shell wizard
  passes the Telegram token and the TTS key to curl through `curl -K -` on stdin, and stores
  them with `envfile.py set` on stdin.
- Error messages are scrubbed of the bot token, the webhook URL and the API key.
- Nothing is sent without an explicit call; `--dry-run` and `--plan` never send.
- By default nothing leaves the machine: the hub listens on 127.0.0.1 only. External
  channels need both credentials and an explicit `NOTIFY_CHANNELS` entry.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "the voice hub is not running" | Run the command it prints: `tools/voice-hub/bin/avh service install` (macOS) or `tools/voice-hub/bin/avh serve`; `avh ping` checks it |
| "no channel" | `NOTIFY_CHANNELS=none` or `VOICE_HUB=off` with nothing else listed; `notify-setup.sh --show` |
| A new browser tab opens for every note | Keep one hub tab open (it takes the next notes), or `VOICE_HUB_OPEN=never` |
| The note arrives as text, or the hub gets nothing | The engine failed: read stderr; Google key (`tts-set-api-key.sh`), gcloud login, or `brew install ffmpeg` for `say` |
| Telegram hangs or times out | The network blocks `api.telegram.org` (some managed networks and security tools do); stay on the hub |
| Chat shows the caption but no audio | No `GCHAT_SPACE`, or `gchat.py login` missing; the webhook alone cannot upload files |
| The hook blocks a turn that sent a note | The send failed: check `voice.log` for `sent note`; after 3 blocks the turn ends anyway |
| The hook never fires | No `notify.env` yet or `NOTIFY_CHANNELS=none` (it is inert), or `[hooks] voice-summary-stop = false` |

## Dependencies

`python3`, `curl`, `ffmpeg` (Homebrew `ffmpeg`, with libopus; libx264 for the Chat
waveform clip). Optional: `say` (macOS), `gcloud`.
