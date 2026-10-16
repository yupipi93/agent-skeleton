---
description: Never write the em dash character (U+2014) in generated text; use a comma, colon, parentheses or a hyphen.
apply: always
---

# No em dash in generated text

Do not write the Unicode em dash (U+2014) in anything you generate: chat replies,
messages drafted for others, tickets, PR titles and bodies, commit messages, docs.
Many readers see it as a sign of machine-written text.

| Intent | Use instead |
|---|---|
| Pause or aside | comma, period or parentheses |
| Label then detail | colon |
| Range or compound | ASCII hyphen `-` |
| List separator | comma or semicolon |

Example: write `Cloud Run (service): closest match` instead of joining the two parts
with an em dash.

Before sending outbound text, scan it. The text guard can enforce this:
`kit/bundles/core/scripts/text-guard.sh --em-dash --file draft.md`.

Do not rewrite em dashes in third-party files you are not editing.
