---
description: Long, complex or decision turns end with a spoken summary sent by voice-note.py.
apply: always
---

# Send a spoken summary at the end of long tasks

When a turn is **long** (4 minutes or more), **complex** (15 tool calls or more, or work
delegated to a subagent), **ends in a decision** (an approval, a command for the user to
run, a choice), or the written reply is **1200 characters or more**, send a voice note
before finishing:

```bash
kit/bundles/voice/scripts/voice-note.py --source <TAG> --title "<short title>" "<spoken summary>"
```

- Write it for the ear (skill `voice-summary`): conclusion first, narrated, one to four
  minutes, ending with what you need from the user.
- Never read commands, paths, hashes or ids aloud. A command for the user goes to the
  channel with `notify.sh --code-only` **and** into your reply as a fenced block.
- The note goes to the local voice hub (the default). Paste the `Markdown:` hub link it
  prints into your reply. If it says the hub is not running, give the user the start
  command it printed. Never add `--to telegram` or `--to chat` unless the user asked.
- Do not send one for answers that fit in a glance.
- Skip it for one turn when the user writes **"no audio"** (the phrase is configurable,
  `VOICE_HOOK_OPTOUT`).

The thresholds live in `~/.config/agent-skeleton/notify.env` (`VOICE_HOOK_*`). The Stop
hook `voice-summary-stop` enforces this where the tool supports it; it is inert until the
bundle is configured (`bin/skeleton setup voice`).
