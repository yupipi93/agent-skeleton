---
description: Write prose like a person, not a chatbot; no AI-writing tells (puffery, not-X-but-Y, AI vocabulary, chatbot openers and closers).
apply: always
---

# Plain human prose

Everything you write for a person (replies, docs, tickets, PRs, commits, messages) avoids
the tells that mark text as machine-written:

- No openers or closers addressed to the reader: "Certainly!", "Great question",
  "I hope this helps", "Let me know if", "¡Claro!", "No dudes en". Start with the
  answer; end on the last fact.
- No puffery: "serves as", "plays a crucial role", "a testament to", "evolving
  landscape", "desempeña un papel fundamental". Use `is` and the fact.
- No staged contrasts ("not just X, it's Y", "no solo X sino Y"), reflex triads, or
  participle tails (", highlighting ...", ", garantizando ...").
- Go easy on the AI vocabulary: delve, crucial, pivotal, robust, foster, leverage,
  seamless, tapestry, underscore; "fundamental", "potenciar", "cabe destacar".
- No "In summary" / "En resumen", no "It's important to note" / "Es importante
  destacar". Name sources instead of "experts say".
- Sentence-case headings, bold rarely, lists only for real lists, straight quotes.

For a draft that leaves the machine, run
`kit/bundles/style/scripts/ai-tells.py draft.md` and rewrite what it flags; the skill
`human-writing` has the full catalogue and rewrites.
