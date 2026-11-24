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
| `plain-human-prose` | Short text within a budget per kind; no chatbot openers or closers, puffery, staged contrasts, AI vocabulary or summary outros |

## Skills

| Skill | Use it for |
|---|---|
| `human-writing` | How a person writes (14 principles), character budgets and how to cut, the full catalogue of AI-writing tells in English and Spanish, before/after rewrites, a self-check |

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/style/scripts/ai-tells.py` | Flag the tells in a draft: HARD (chatbot artifacts, placeholders, em dash, cutoff lines, sycophantic openers), WARN (puffery, not-X-but-Y, participle tails, weasel words, AI-vocabulary density, Title Case headings, inline-header lists, uniform sentence length) |

| `kit/bundles/style/scripts/text-budget.py` | Keep a draft as short as possible: warn over its kind's target (chat 80 characters, comment 120, email 250, PR, ticket and reply 300, voice 500) and block over the maximum (chat 200, comment 250, email 450, PR and ticket 500, reply 600, voice 900); code, URLs and Markdown markup are not counted |

```bash
kit/bundles/style/scripts/ai-tells.py draft.md            # exit 0 clean, 1 warnings, 2 hard
kit/bundles/style/scripts/ai-tells.py --lang es draft.md  # Spanish word lists only
kit/bundles/style/scripts/text-budget.py --kind chat draft.md  # exit 0 ok, 1 over target, 2 over max
kit/bundles/style/scripts/text-budget.py --list           # targets and maximums in force
```

Override per kind with `TEXT_TARGET_<KIND>` and `TEXT_BUDGET_<KIND>` (maximum) in the
environment or in `~/.config/agent-skeleton/style.env`, or the maximum once with `--max N`.

Fenced code, inline code and `>` quotes are skipped for prose checks; chatbot artifacts
are searched everywhere. The format checks target text for people: skills and runbooks
written for agents use bold labels on purpose.

Outbound text can also be checked for the em dash alone with
`kit/bundles/core/scripts/text-guard.sh --em-dash --file draft.md`.

The kit itself never contains the em dash, whether this bundle is on or not:
`bin/skeleton check` rejects it in every tracked file.
