# Catalogue of AI-writing tells

Condensed from Wikipedia's field guide
[Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
(WikiProject AI Cleanup, read 2026-10). Section shortcuts such as `WP:AIVOCAB` point to
the matching part of that page. Every item lists what the tell is and what a person would
write instead.

The guide's own caveat applies: one tell proves nothing; people use all of these words.
What gives text away is **density** (several tells in one paragraph) and **fit** (the
phrase adds tone but no fact).

## 1. Content

| Tell | Words to watch | Write instead |
|---|---|---|
| Inflated significance | stands as, serves as, is a testament / reminder, plays a crucial / pivotal / vital / key role, underscores / highlights its importance, reflects broader, symbolizing its enduring / lasting, setting the stage for, marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted | The fact itself. If the significance is real, cite who said so; otherwise delete the sentence |
| Notability by media list | independent coverage, featured / profiled in, national media outlets, trade publications, active social media presence, written by a leading expert | Say what the source reported, not that it exists |
| Superficial analysis in a participle tail | `..., highlighting / underscoring / emphasizing / ensuring / reflecting / symbolizing / contributing to / fostering / cultivating / encompassing / enhancing ...`, valuable insights, align / resonate with | End the sentence at the fact. A consequence goes in its own sentence with its evidence |
| Promotional tone | boasts, vibrant, rich, profound, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking, renowned, featuring, diverse array | Neutral description: size, date, what it does. Let the reader judge |
| Vague connection (`WP:AICONNECT`) | in connection with, connected to, in association with, (particularly / widely) associated with | The actual relation: owns, founded, wrote, depends on |
| Weasel attribution (`WP:AIWEASEL`) | experts argue, observers have cited, some critics argue, industry reports, several sources (when there are two), "such as" before a list that is in fact complete | Name the source, or drop the claim |
| Challenges-and-outlook outline (`WP:FACESCHALLENGES`) | Despite its ... faces several challenges, Despite these challenges, Challenges and Legacy, Future Outlook | Specific problems with dates, no upbeat closer |
| "X and Y" headings | Awards and recognition, Legacy and impact | One-topic headings, or no heading |

## 2. Language and grammar

**AI vocabulary** (`WP:AIVOCAB`): words whose frequency jumped after 2022. One is
nothing; four in a paragraph is a signature.

| Era (model) | Overused words |
|---|---|
| Core list | additionally, align with, boasts, bolstered, crucial, deep dive, delve, emphasizing, enduring, enhance, fostering, garner, highlight, interplay, intricate / intricacies, key, landscape, meticulous / meticulously, pivotal, robust, showcase, tapestry, testament, underscore, valuable, vibrant |
| 2023 to mid-2024 (GPT-4) | additionally, boasts, delve, garner, intricate, interplay, meticulously, tapestry, testament |
| Mid-2024 to mid-2025 (GPT-4o) | align with, enhance, fostering, highlighting, pivotal, showcasing, underscore |
| Mid-2025 to mid-2026 (GPT-5) | emphasizing, enhance, highlighting, showcasing, plus the notability words above |
| Mid-2026 on (GPT-6) | challenge, clearer, dependable, echoed, foster, leverage, matters, multifaceted, practical, prioritize, quietly, steady, universally; also many short sentences of a uniform 8 to 20 words |
| Grok | causal, empirical, correlate, underscore |

Other grammar tells:

| Tell | Pattern | Write instead |
|---|---|---|
| Avoided copula (`WP:AINOCOPULA`) | serves as, stands as, functions as, operates as, represents, boasts, features, maintains, offers; a lead that "refers to" | `is`, `has`. "The library is the town's archive", not "serves as" |
| Negative parallelism (`WP:AIPARALLEL`) | not only ... but also; it's not just X, it's Y; not X, but Y; X. Rather, Y; no X, no Y, just Z | Say Y. Nobody claimed X |
| "Y rather than X" | prioritizing A rather than B | State the choice; mention the rejected option only if someone proposed it |
| Rule of three (`WP:RO3`) | triads of adjectives or short phrases: fast, reliable and scalable | One precise word, or as many items as really exist |
| Title as a proper noun | "List of X is the chronological list of", "X refers to" | Start with the subject itself |
| Slogan rhetoric | contrast pairs, a punchy one-line closer, abstract theory framing ("performative enactment of") | Plain argument; end on the last fact |
| Uniform rhythm | every sentence 8 to 20 words, every paragraph three sentences | Mix: a four-word sentence, then a long one with a clause |

## 3. Style and formatting

| Tell | Shortcut | Write instead |
|---|---|---|
| Title Case Headings | `WP:AITITLECASE` | Sentence case: "Impact of technology" |
| Boldface sprinkled on key terms | `WP:AIBOLD` | Bold at most one warning per section, or none |
| Inline-header lists: `- **Label:** text` | `WP:AILIST` | Prose, or a table when items share columns |
| Bullets made of `•` or `–` characters | `WP:AILIST` | Real Markdown list markers |
| Emoji before headings or bullets (wave, brain, globe, target, siren, compass) | `WP:AIEMOJI` | No emoji, unless a house convention asks for one (a status line, a chat message) |
| Small two-column tables ("Metric / Figure") | `WP:AITABLE` | A sentence |
| Curly quotes and apostrophes (U+201C, U+201D, U+2018, U+2019), sometimes mixed with straight ones | `WP:AICURLY` | Straight `"` and `'` in Markdown, code and plain text. Spanish typography (`« »`) is fine |
| Heading that repeats the title, skipped levels, a heading with only subheadings, level 1 everywhere | heading errors | One `#` title, then `##`, each heading followed by text |
| Thematic breaks `---` between every section | `WP:MARKDOWN` | Headings alone separate sections |

## 4. Talking to the user inside the deliverable

| Tell | Words to watch | Write instead |
|---|---|---|
| Collaborative chatter (`WP:COLLABCOMM`) | Certainly!, Of course!, You're absolutely right!, Great question, I hope this helps, Would you like..., is there anything else, let me know, here is a ..., a more detailed breakdown | Nothing. Start with the answer, stop after it |
| Source-availability hedges (`WP:AIDISCLAIMER`) | While specific details are limited, not widely documented, based on available information, in the provided sources, does not by itself establish | Say what you know; mark a single unknown once ("not verified") |
| Placeholders (`WP:AIPLACEHOLDER`) | [Your Name], [Describe ...], INSERT_SOURCE_URL, 2025-XX-XX, (Add your URL here) | Fill it, or ask for the value before sending |
| Letter openings in comments | Dear ... Team, I am writing to, I hope this message finds you well, I understand your concern | Get to the point in the first line |
| Customer-service tone | apologise for the inconvenience, I have carefully reviewed, happy to fix if you point it out | State what you checked and what you found |

## 5. Machine artifacts (proof, not style)

These only come from a chatbot copy-paste. Never leave one in a deliverable.

- ChatGPT: `contentReference`, `oaicite`, `oai_citation`, `turn0search0`, `attributableIndex`.
- Gemini: `[cite: 1]`, `[span_1](start_span)`.
- Grok: `grok_card`, `grok_render_citation_card_json`.
- DeepSeek: lenticular brackets with daggers, `【85†L261-269】`.
- Perplexity: `[attached_file:1]`, `[web:1]`, `ppl-ai-file-upload`.
- Unclassified: `:::writing{variant="document"}`.
- Link trackers: `utm_source=openai`, `utm_source=chatgpt.com`, `utm_source=copilot.com`, `referrer=grok.com`.
- The footnote return arrow `↩` copied from another site.
- Markdown in a system that does not render it (`**bold**`, `##`, `[text](url)` in wikitext or a plain-text field).

## 6. Citations and links

- Dead or invented URLs, ISBNs with bad checksums, DOIs that resolve to an unrelated paper.
- A real book cited for a claim it does not make, no page number, no URL.
- References declared and never used; the same reference repeated after every sentence.

Check every link and identifier you did not copy from a source you opened yourself.

## 7. Change descriptions (edit summaries, commit messages, PR bodies)

| Tell | Words to watch | Write instead |
|---|---|---|
| Compliance boilerplate | ensured, adheres to, refined, enhanced, streamlined, in compliance with, clarity, flow, neutral tone | What changed: "move the retry loop into the client" |
| Listing what was kept | preserved, retained, avoided, aimed to | Only what changed; the diff shows the rest |
| Citation bragging | added sourced, added verified, improved attribution, peer-reviewed sources | The content that was added |
| Markup inventory | parameter names, "inline citations", "internal links" | The user-visible effect |
| "Addressed the reviewer's feedback" | | Which comment, what fix |

## 8. Historical tells (rarer in new models, still worth removing)

| Tell | Years | Words to watch |
|---|---|---|
| Knowledge-cutoff disclaimers | 2022 to 2023 | as of my last knowledge update, up to my last training update |
| Didactic disclaimers | 2022 to 2024 | it's important / crucial to note, it's worth noting, may vary |
| Section summaries | | In summary, In conclusion, Overall |
| Em dash overuse (U+2014), usually spaced on both sides | 2022 to September 2026 | the character itself; models from late 2026 are reportedly trained to avoid it |
| Abrupt cut-off | | continue generating |
| Elegant variation: a new synonym each time the subject comes back | | Repeat the noun. "The bridge ... the bridge", not "the structure ... the span" |

## 9. What reads human (the guide's own list)

- Plain copulas: "there is a", "it has a".
- Plain verbs: wrote (not authored), moved (not relocated), used (not utilized), tried (not
  attempted), died (not passed away).
- Commitment: "one of the best", "the only", "the first", when true.
- Ordinary qualifiers: very, perhaps, tends to.
- Some looseness: "in order to", "as a result of", "the fact that" are human habits; do not
  scrub every one of them out.

## 10. Not tells on their own

Perfect grammar, mixed registers, bland prose, formal or academic vocabulary in general,
transition words alone ("Additionally", "Notably"), unsourced text and correct markup.
Removing these does not make text more human; removing the tells above does.
