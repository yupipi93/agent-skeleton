# BACKLOG.md template

Copy this into `<deliverable folder>/BACKLOG.md` and replace the placeholders.

```markdown
# <Tool name>: backlog

Requests and audit findings not done yet. Move an item to "Done" with the release when
it ships. IDs are never reused.

## Open

| ID | Origin | What | Design |
|---|---|---|---|
| B-14 | user, 2026-01-15 | Filter the list by owner | Owner chips above the list; one click filters, a second click clears; the filter lives in the URL hash so links keep it |
| B-15 | audit 6 | Long names overflow the card on phones | Clamp to two lines with an ellipsis and a `title` with the full name |

## Done

| ID | Release | What |
|---|---|---|
| B-13 | 7 | Saved filters per user, stored server side, listed in the filter menu |
| B-12 | 7 | CSV export of the current view (columns as shown, UTF-8 with BOM) |
| B-09 | - | Dropped: replaced by B-12 (user, 2026-01-12) |
```

## Rules

- **Origin** says who asked and when (`user, <date>`), or `audit N` for a deferred
  finding of the auditor of release N.
- **Design** is written before the code: the intended behaviour, UI, API or data shape in
  one or two sentences. If you cannot write it, ask the one question that unblocks it.
- **Done / What** says what actually shipped, which may differ from the design. Keep it
  to one line; the commit has the detail.
- Newest releases first in Done.
- Keep the file in the same repository and commit as the code it describes, so a later
  session finds the open work without the chat history.
