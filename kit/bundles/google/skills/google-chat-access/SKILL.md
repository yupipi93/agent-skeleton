---
name: google-chat-access
description: "Read and write the user's Google Chat (spaces, threads, DMs, send and reply as them) with kit/bundles/google/scripts/gchat.py. Use when asked to check, search, summarise, quote, reply to or send something in Google Chat, or to set up or debug that access."
---

# Google Chat access

```bash
kit/bundles/google/scripts/gchat.py whoami                          # your users/ID
kit/bundles/google/scripts/gchat.py spaces --type SPACE --name "release"
kit/bundles/google/scripts/gchat.py find-dm someone@example.com     # the 1:1 DM space
kit/bundles/google/scripts/gchat.py messages spaces/AAAA1234 --limit 30 --mark-me
kit/bundles/google/scripts/gchat.py send spaces/AAAA1234 --text-file draft.md --dry-run
kit/bundles/google/scripts/gchat.py send spaces/AAAA1234 --text-file draft.md
kit/bundles/google/scripts/gchat.py send spaces/AAAA1234 --text "ok" --thread spaces/AAAA1234/threads/BBBB
kit/bundles/google/scripts/gchat.py search --keywords release notes --days 30
kit/bundles/google/scripts/gchat.py probe-write spaces/AAAA1234     # posts nothing
```

Add `--json` to read commands when you parse rather than show. The token refreshes
itself; "not logged in" means run `kit/bundles/google/scripts/gchat.py login` (setup:
`docs/bundles/google.md`). Chat requires a Google Workspace account.

## Rules when acting on the user's Chat

1. **Messages go out as the user**, not as a bot (user OAuth, `sender.type: HUMAN`).
2. **Never send to other people without showing the exact draft first** and getting a
   yes. Reading a thread to draft a reply is fine. A space where the user is the only
   member needs no approval. Use `send --dry-run` to show the request.
3. **Scan outbound text** for secrets first: `kit/bundles/core/scripts/text-guard.sh --file draft.md`.
4. **If asked to disclose you are an AI, say it in the message body**: the sender field
   cannot carry it.
5. **Do not answer what you lack context for**; defer to the user.
6. **Chat holds confidential material.** Do not copy it into tickets, PRs or other
   services unless asked.

## Formatting

`gchat.py send` always sets `markupSyntax: MARKUP_SYNTAX_MARKDOWN`. Without that field the
API accepts `*bold*`, echoes success, and never parses it (the message shows literal
asterisks; `formattedText` equals `text`). If you POST yourself with
`gchat.py token` and curl, add the field. Under Markdown syntax:

| Want | Write |
|---|---|
| bold | `**bold**` (a single `*` is italic) |
| italic | `*italic*` or `_italic_` |
| strike | `~~text~~` |
| code | `` `code` `` and fenced blocks |
| list | `- item`, `1. item` |
| link | `[label](https://example.com)` or the bare URL |

Single newlines collapse under Markdown; `send` turns `•` lines into `- ` items and adds a
blank line between other lines. Write one idea per block: short paragraphs, a bold lead
word, a short list instead of a dense paragraph. To check how a sent message really
renders, read `formattedText` in `messages --json`.

## Gotchas

- **403 means nothing on its own.** Chat answers `PERMISSION_DENIED` both for "denied"
  and for "no such space". `probe-write` posts with an invalid `messageId`: a 400 proves
  you may post, and nothing is created.
- **No "note to self" DM** through the API. For a harmless write target, create a
  single-member space (`create-space --name "Agent scratch"`).
- **No "get my user id" endpoint.** `whoami` intersects the human members of a few DMs.
- **No server-side message search** in the REST API: `search` scans spaces (slow); narrow
  it with `--space-name`, `--days` and `--per-space`.
- **Threads:** pass `--thread` only when the user wants an in-thread reply.
- **One login at a time:** each login listens on a loopback port until the browser returns.
