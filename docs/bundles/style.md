# ✒️ style

Off by default. House style for generated text: no em dash, and prose that reads like a
person wrote it, based on Wikipedia's field guide
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).

```bash
bin/skeleton enable style
```

## Rules

| Rule | In short |
|---|---|
| `no-em-dash` | Never write U+2014; use a comma, colon, parentheses or `-` |
| `plain-human-prose` | No chatbot openers or closers, puffery, staged contrasts, AI vocabulary or summary outros |

## Skills

| Skill | Use it for |
|---|---|
| `human-writing` | How a person writes (13 principles), the full catalogue of AI-writing tells in English and Spanish, before/after rewrites, a self-check |

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/style/scripts/ai-tells.py` | Flag the tells in a draft: HARD (chatbot artifacts, placeholders, em dash, cutoff lines, sycophantic openers), WARN (puffery, not-X-but-Y, participle tails, weasel words, AI-vocabulary density, Title Case headings, inline-header lists, uniform sentence length) |

```bash
kit/bundles/style/scripts/ai-tells.py draft.md            # exit 0 clean, 1 warnings, 2 hard
kit/bundles/style/scripts/ai-tells.py --lang es draft.md  # Spanish word lists only
```

Fenced code, inline code and `>` quotes are skipped for prose checks; chatbot artifacts
are searched everywhere. The format checks target text for people: skills and runbooks
written for agents use bold labels on purpose.

Outbound text can also be checked for the em dash alone with
`kit/bundles/core/scripts/text-guard.sh --em-dash --file draft.md`.

The kit itself never contains the em dash, whether this bundle is on or not:
`bin/skeleton check` rejects it in every tracked file.
