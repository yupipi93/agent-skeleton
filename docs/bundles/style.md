# ✒️ style

Off by default. Optional house-style rules for generated text.

| Rule | In short |
|---|---|
| `no-em-dash` | Never write U+2014; use a comma, colon, parentheses or `-` |

Enable it with `bin/skeleton enable style`. Outbound text can be checked mechanically
with `kit/bundles/core/scripts/text-guard.sh --em-dash --file draft.md`.

The kit itself never contains the character, whether this bundle is on or not:
`bin/skeleton check` rejects it in every tracked file.
