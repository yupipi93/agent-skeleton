---
name: human-writing
description: "Write short prose that reads like a person wrote it: AI-writing tells from Wikipedia's Signs of AI writing, character budgets per kind of text, two checker scripts. Use when drafting docs, tickets, PRs, emails or messages, or when a draft sounds AI-written or long."
---

# Human writing

Readers now spot machine text in a sentence or two, and once they do they stop trusting
the rest. This skill describes how a person writes, lists the tells that give a machine
away, and ships a checker (`kit/bundles/style/scripts/ai-tells.py`) that flags them in a
draft before it leaves the machine.

Source: Wikipedia's field guide
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).
The full catalogue, section by section, is in
[references/ai-writing-tells.md](references/ai-writing-tells.md); the Spanish forms are in
[references/spanish.md](references/spanish.md).

## When to use

- Any prose a person will read: docs, READMEs, ADRs, ticket descriptions and comments,
  PR bodies, commit messages, chat messages, emails, release notes.
- Reviewing a draft (yours or someone else's) that "sounds like ChatGPT".
- Not for code, config or machine output quoted verbatim.

## How a person writes

1. **Start with the point.** The first sentence is the answer, the result or the request.
   No preamble, no `Here is a summary of`.
2. **Concrete beats abstract.** Names, numbers, dates, versions, file paths. "Tokens
   expire after one hour` instead of `enhanced security posture".
3. **Plain verbs, plain copula.** `is`, `has`, `uses`, `moved`, `wrote`. Not `serves as`,
   `boasts`, `leverages`, `utilizes`.
4. **Say it once.** No intro that announces the content, no outro that repeats it, no
   `In summary`.
5. **State things, do not stage them.** Skip `not X, but Y` when nobody said X. Skip the
   triad of adjectives when one is accurate.
6. **Let the facts carry the weight.** No `crucial`, `pivotal`, `testament`, `vibrant`.
   If something matters, the reason it matters is the sentence.
7. **Attribute or drop.** `The 2025 audit found`, not `experts argue`. One source is one
   source, not `several`.
8. **Uncertainty once, specifically.** `Not tested on pro yet` beats three hedges spread
   across the text.
9. **Vary the rhythm.** A four-word sentence after a long one. Paragraphs of different
   sizes. Uniform 15-word sentences are a tell in themselves.
10. **Repeat the noun.** Call the gateway `the gateway` every time; swapping in "the
    component`, `the solution`, `the platform" is elegant variation and reads machine-made.
11. **Format for the reader, not for show.** Prose for reasoning, a list only for things
    that are really parallel, a table only when items share columns. Sentence-case
    headings. Bold for one thing per section at most. No emoji on headings or bullets
    unless the house convention asks for them.
12. **End on the last fact.** No offer, no `let me know if`, no `I hope this helps`.
13. **Keep the human texture.** Contractions in informal text, `very` and `perhaps` where
    they fit, an occasional `in order to`. Do not scrub prose into telegraphese, and do
    not fake typos or slang to look human.
14. **Write it short.** A person writes the two lines that matter; a machine writes the
    twenty around them. Readers lose the thread past a few lines, so keep the ask and
    the facts and link the rest.

## Length budget

Every kind of text has a **target**, what a person would write, and a **maximum**, a
ceiling never to be filled. Start from the target: write the one-line version first and
add only what the reader cannot act without. `text-budget.py` counts only what a person
reads (fenced code, URLs and Markdown markup are free); it exits 1 over the target
(shorten it if you can) and 2 over the maximum (cut it):

| Kind | Target | Max |
|---|---|---|
| `chat` (Chat, Teams, Slack) | 80 | 200 |
| `notify` (push) | 80 | 160 |
| `commit` (subject + body) | 100 | 250 |
| `comment` (ticket, PR) | 120 | 250 |
| `email` (body) | 250 | 450 |
| `pr` (body), `ticket` (description) | 300 | 500 |
| `post` (social), `reply` (agent to its user) | 300 | 600 |
| `voice` (spoken) | 500 (30 s) | 900 (60 s) |

Override per kind with `TEXT_TARGET_<KIND>` and `TEXT_BUDGET_<KIND>` (maximum) in the
environment or in `~/.config/agent-skeleton/style.env`, or once with `--max N` when the
user asked for a long text (a report, a "con detalle" summary). Docs and READMEs have no budget, but the
same habit applies: one idea per paragraph, delete what does not change a decision.

How to cut, in order:

1. Delete what the reader already knows or does not need to act: background, how it was
   found, who said what, the steps you took.
2. Move detail to the ticket, PR or doc and put the link in the text.
3. One fact per line; numbers instead of adjectives.
4. Several unrelated points: several short messages, not one long one.

## Steps

1. Draft the text in a file (it is going to be scanned anyway, see the outbound text
   rules).
2. Run the checker:

   ```bash
   kit/bundles/style/scripts/ai-tells.py draft.md            # English and Spanish lists
   kit/bundles/style/scripts/ai-tells.py --lang es draft.md  # one language only
   ```

   Exit 0 is clean (or notes only), 1 means warnings to rewrite, 2 means a HARD finding
   (chatbot artifact, placeholder, em dash, knowledge-cutoff line, sycophantic opener).
   Then the length: `kit/bundles/style/scripts/text-budget.py --kind chat draft.md`
   (exit 1 shorten if you can, exit 2 cut; see "Length budget").
3. Fix every HARD finding and every overrun of the maximum; get under the target when
   nothing the reader needs is lost. Rewrite each WARN using the table below; a warning you keep
   needs a reason (a quoted title, a product name in a heading).
4. Read the text once as the recipient. Would a colleague write this sentence in this
   channel? If it sounds like a brochure or a support bot, cut it.
5. Re-run the checker, then send through the normal outbound gate (secret scan, approval).

## Rewrites

| Machine | Human |
|---|---|
| `Certainly! Here is a summary of the migration.` | The migration is done. |
| `The gateway serves as a pivotal component, underscoring our commitment to security.` | The gateway checks every token before a request reaches the API. |
| `It's not just a proxy, it's a platform.` | It also handles rate limits and logging. |
| `- **Security:** robust and seamless authentication.` | Logins go through Google SSO; sessions expire after one hour. |
| `Experts argue this is best practice.` | Google's Cloud Run docs recommend it (link). |
| `It's important to note that results may vary.` | Pro has not been load-tested yet. |
| `In conclusion, the gateway is ready. Let me know if you have questions!` | Rollback: point the DNS record back at the VM. |
| `No se trata solo de un cambio técnico, sino de una transformación cultural.` | El cambio obliga a los equipos a pedir acceso por ticket. |
| `Cabe destacar que desempeña un papel fundamental en la arquitectura.` | Todo el tráfico de pro pasa por él. |
| `Ensured clarity, refined wording and preserved the existing structure.` (commit) | Shorten the install section and fix the broken link. |

## Self-check before sending

- Does the first sentence say the thing?
- At or near its target, never over the maximum (`text-budget.py`)?
- Could any sentence be deleted without losing a fact? Delete it.
- Any word from the vocabulary list where a plain one works?
- Any `not X but Y`, triad, or participle tail (`..., highlighting ...`)?
- Any claim without a name, number or source behind it?
- Headings in sentence case, bold rare, lists only for real lists?
- Does it end on a fact rather than an offer or a summary?

## Gotchas

- **The checker is a smoke detector, not a judge.** One `robust` in a page is fine; the
  vocabulary check only warns on density. Product names trip the Title Case check
  (`Terraform on Google Cloud`); keep them and move on.
- **Reference docs for agents are different.** Bold labels and `- **Label:**` lists help an
  agent scan a skill or a runbook; the format warnings are aimed at text for people.
- **House conventions win.** A chat template with an emoji status line or a ticket
  template with fixed bold labels stays as the house wants it.
- **Code is skipped.** Fenced blocks, inline code and `>` quotes are not scanned for
  prose tells, so quote machine output there. Chatbot artifacts (citation markers, chat
  link trackers) are searched everywhere, because they are never legitimate in a deliverable.
- **No em dash** (U+2014): the `no-em-dash` rule in this bundle applies, and the kit's
  `bin/skeleton check` rejects the character in tracked files.
- **Do not overcorrect.** The guide lists perfect grammar, formal vocabulary and
  transition words as weak signals on their own. Removing tells makes text human;
  sanding off every connective makes it robotic in a new way.
