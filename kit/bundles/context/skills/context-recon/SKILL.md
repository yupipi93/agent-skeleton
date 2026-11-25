---
name: context-recon
description: Find what the workspace already knows before acting - one search over memory, notes, wikis, repo docs, past sessions and app stores, plus live Jira, chat and mail. Use at the start of a ticket, change or mission, or for 'what do we know about', 'search everything', 'get up to speed'.
---

# Context recon

The rule `context-recon-first` says when and how deep. This skill is the how: the
index, the sources, the queries and the deep-recon subagent.

## The tool

`kit/bundles/context/scripts/ctx.py` (stdlib, Python 3.11+, read-only on every source).

| Command | What it does |
|---|---|
| `ctx.py search "terms" [--source a,b] [--since 30d] [--limit 10] [--json]` | Ranked hits with snippet and path or id |
| `ctx.py show <handle> [--full]` | The indexed text of one hit: `source:row-id` handles from pointers (rows of app databases) stay valid; numeric `#id`s from `search` only until the next refresh |
| `ctx.py brief "task text"` | What the prompt hook would inject: entities, live sources to check, top pointers |
| `ctx.py live "terms" [--source jira]` | Runs the live sources now (not indexed) |
| `ctx.py sources` | Configured sources, document counts, newest date, last index run |
| `ctx.py index [--source id] [--full]` | Refresh the index (incremental; the hook starts one in the background when it is older than 30 min) |

The index lives in `~/.cache/agent-skeleton/context/index-<hash>.db`, one per checkout and
Claude projects dir (`ctx.py sources` prints it; SQLite FTS5, accents
ignored, no stemming, so Spanish and English both work).

## Sources

`ctx.py sources` lists the real set on this machine. Defaults in the kit:

| id | What | Best for |
|---|---|---|
| `memory` | Agent memory notes (`$CLAUDE_CONFIG_DIR` or `~/.claude`, `projects/*/memory`) | Decisions, gotchas, who owns what, past incidents |
| `sessions` | Past agent sessions: title, first prompts, last answer | "We did this before": what was tried, where it ended |
| `workspace` | AGENTS.md, docs/, plans/ | How this workspace works |
| `skills` | Skill bodies, references and rules | Which procedure applies |
| `repos` | README, AGENTS, BACKLOG, docs/ and ADRs of every repo under `projects/` | Architecture and conventions of a codebase |
| `jira` (live) | JQL text search | Current ticket state |

Overlays add their own in `local/bundles/<b>/context/sources.toml` (notes vaults,
meeting transcripts, wikis, chat and mail CLIs, app databases) and an entity glossary
(`[[entity]]`: a client, product or person with its aliases, skills, paths, board and
live sources). The format is documented at the top of
`kit/bundles/context/sources.toml`.

## Writing queries

- Search by **names and ids first**: ticket keys, repo, service, GCP project, person.
  A key `PROJ-42` is matched as a phrase and outranks everything else.
- Then **two or three phrasings**: Spanish and English, the product name and its repo
  name, the symptom and the component (`deploy gates`, `quality gate api-gateway`).
- Narrow with `--source` (`--source memory,sessions` for "did we decide this?",
  `--source meetings --since 14d` for "what was said") and `--since`.
- Read the hit, not the snippet: `Read` the path, `ctx.py show <handle>` for the rest. A
  session hit gives the transcript path: `grep` it for the detail you need.
- Live sources: pass 1-3 precise words (`ctx.py live "nginx patch" --source jira`).
  Chat search is slow (up to 40 s); run it only when the people matter.

## Deep recon (missions, unfamiliar areas)

Launch one read-only subagent (Explore or general-purpose) in the background while you
start on what is clear. Brief it with the goal, not your hypotheses:

```text
Recon for: <the task in one paragraph>.
Sweep every knowledge source and return a dossier, max 400 words, each fact with its
source path or id and date:
1. kit/bundles/context/scripts/ctx.py sources, then ctx.py search with at least 5
   phrasings (names, ids, Spanish and English), each source family at least once.
2. Read the top hits in full (Read / ctx.py show), plus the repo's README, AGENTS.md,
   docs/ index, ADRs and git log -20 if a repo is involved.
3. ctx.py live for the tickets and people involved.
4. Report: what is known, decisions already taken, open items, contradictions between
   sources (say which is newer), and what is still unknown.
Read-only: change nothing, send nothing.
```

Use its dossier as data: verify the facts you act on.

## Keeping it useful

- Write durable findings back (memory, repo docs, the ticket): the next session's recon
  is only as good as what this one leaves behind.
- A source that keeps returning noise: add an `exclude` (or `extend = true` with more
  excludes) in its overlay file; a missing client or product: add an `[[entity]]`.
- `ctx.py index --full` after changing include or exclude patterns.
