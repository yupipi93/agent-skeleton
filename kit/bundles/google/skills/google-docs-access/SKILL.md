---
name: google-docs-access
description: "Find, read, export and edit the user's Google Docs (Drive search, read, export, create, append, replace, batchUpdate) with kit/bundles/google/scripts/gdocs.py. Use when asked to find, read, summarise, draft or edit a Google Doc, or to set up or debug that access."
---

# Google Docs access

```bash
kit/bundles/google/scripts/gdocs.py search --name "roadmap"
kit/bundles/google/scripts/gdocs.py search --content "release checklist" --limit 10
kit/bundles/google/scripts/gdocs.py info <doc>                # owner, dates, canEdit, URL
kit/bundles/google/scripts/gdocs.py get <doc>                 # plain text, tables flattened
kit/bundles/google/scripts/gdocs.py get <doc> --raw           # full Docs JSON (indexes, styles)
kit/bundles/google/scripts/gdocs.py export <doc> --format md --out notes.md   # md txt html pdf docx odt rtf epub
kit/bundles/google/scripts/gdocs.py create --title "Scratch" --text "hello"
kit/bundles/google/scripts/gdocs.py append <doc> --text "one more line"
kit/bundles/google/scripts/gdocs.py insert <doc> --index 1 --text "at the top "
kit/bundles/google/scripts/gdocs.py replace <doc> --find OLD --replace NEW
kit/bundles/google/scripts/gdocs.py batch-update <doc> requests.json
kit/bundles/google/scripts/gdocs.py probe-write <doc>         # prove write access, change nothing
kit/bundles/google/scripts/gdocs.py scopes                    # what the token can do
```

`<doc>` is a document id or any Docs URL. Add `--json` to parse output. "Not logged in"
means run `kit/bundles/google/scripts/gdocs.py login` (setup: `docs/bundles/google.md`).

## Rules when acting on the user's Docs

1. **Every edit is attributed to the user** in the revision history; there is no bot
   identity. Shared documents show it to everyone with access.
2. **Never edit a document the user has not named.** For drafts, `create` a new one.
3. **Read before writing, always.** Index arithmetic depends on the current content: `get
   --raw` right before a `batch-update`, never from memory.
4. **`probe-write` first** when write access is in doubt. It is free and changes nothing.
5. **Drive holds confidential material.** Do not copy it elsewhere unless asked.

## Gotchas

- **Indexes count UTF-16 code units**, not characters: an emoji counts 2. Measure inserted
  text the same way (the script reports UTF-16 lengths).
- **Insert at `endIndex - 1`**, never `endIndex`: the body ends with a newline nothing can
  follow. `append` does this for you; hand-written `batch-update` payloads must too.
- **Prefix inserted text with `\n` to start a new paragraph**; otherwise it continues the
  last one (`append` adds it unless `--no-newline`).
- **Inserted text inherits nearby styling**, which is not a guarantee: follow an insert with
  an explicit `updateTextStyle` over the same range in the same batch to match a look.
- **Edit back to front.** In one `batchUpdate`, apply requests from the highest index to the
  lowest, or each insert shifts the indexes of the next.
- **404 means no such document; 403 means denied.** (Unlike Chat, Docs tells them apart.)
- **Drive `modifiedTime` lags a write by seconds**; the revisions list is authoritative.
- **`export --format txt`** strips the BOM Drive prepends.
