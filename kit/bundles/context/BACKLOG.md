# Context bundle backlog

Items are numbered `CTX-n`. Design first, then code; shipped items move to Done with the
release number (rule `audited-releases`).

## Open

- **CTX-7 Hook outside the workspace.** Sessions started in another directory (a project
  worktree) do not load this repo's hooks. Design: an opt-in user-level hook entry that
  points at the absolute script path, skipped when the project hook already ran.
- **CTX-8 Drafters use the brief.** Reply drafters that gather their own context could
  call `ctx.py brief` for memory, notes and past sessions.
- **CTX-9 Cursor session context.** Check whether Cursor's `sessionStart` can add context;
  if so, render the hook there too.

## Done

### Release 12 (audit of release 11, minor only: no new audit)

- `brief --json` output is cleaned like `search --json`.
- A run that re-read whole sources ends with `VACUUM` (the file was half free pages).
- A partial run stops claiming files at the last requested source's priority.

### Release 11 (audit of release 10)

- A transcript with a lone surrogate (an emoji cut in half) no longer stops the whole
  `sessions` source: text is sanitized and each bad file is skipped and logged.
- At most four common-word phrases per query; a partial run claims files with the same
  size filter as a full one.
- Redaction: values after `${VAR}` or `[redacted`, long names after the keyword, triple
  quotes, unterminated quotes, `<value>` (letters-only placeholders stay), commas inside
  values, `pw=`; text is redacted before it is truncated.

### Release 10 (audit of release 9)

- Redacted: Slack, Teams and Discord webhooks, Telegram bot tokens, URL signatures,
  Tailscale keys, `curl -u`, `docker|sshpass ... -p`, XML password elements, credential
  URLs with an empty user, and "la contraseña es ..." prose.
- `name = value` redaction finds the keyword first and runs in linear time; the
  credential-URL scheme is bounded (long runs of letters no longer cost seconds).
- Prefix terms whose stem is common are dropped too; phrases built from common words never
  count as a strong match; `index --source a,b` accepts commas and rejects unknown ids.

### Release 9 (audit of release 8)

- Hook speed back under half a second on a real index: words in more than 8% of chunks
  are dropped (adjacent ones become a phrase), at most three prefix terms, 15 candidates
  per source, coverage on the first 1500 characters, an ASCII fast path, and FTS5
  optimize or merge after every index run with changes.
- Files are redacted before chunking; long JWTs, GitHub fine-grained, Hugging Face, npm,
  `xoxe` Slack tokens, cookies and long bare `key =` values are covered; changing the
  redaction rules re-reads every source; `search` output is cleaned.
- The group-kill test checks the grandchild's pid instead of a racy marker file.

### Release 8 (audit of release 7)

- Redaction covers JWK private fields, `*_PASS`, `contraseña`/`clave`, `--password value`,
  `ENV name value`, `mysql -p`, YAML block scalars, quoted values with spaces, Stripe and
  GitLab tokens, `Authorization: token`; only `${VAR}`, `$UPPER_VAR`, Secret Manager paths
  and placeholders stay visible.
- Every redaction and heading regex is bounded (no ReDoS); timing tests cover them.
- A changed source definition (`skip_prompts`, excludes, roots) re-reads that source;
  `live` timeouts always end with SIGKILL to the command's own group.

### Release 7 (audit of release 6)

- Redaction has its own case-insensitive credential rule (`DB_PASSWORD=`, `API_KEY:`,
  `aws_secret_access_key =` values) plus OAuth client secrets, `ya29.` tokens and Basic
  auth; Secret Manager paths and `${VAR}` references stay readable. Format 3, tracked per
  source, so a partial run re-reads only its own sources.
- `*/dir/*` excludes and includes also match folders at the top of a root.
- `show` and `search --json` output is cleaned; an existing `CTX_HOME` keeps its mode;
  only `CTX_NO_SPAWN=1` disables the background run.

### Release 6 (audit of release 5)

- Secret-shaped strings (the core bundle's patterns plus private-key blocks) are redacted
  when indexed and again in pointers, `live` and `show`; an index format bump re-reads
  everything once.
- With `ticket_prefixes`, keys inside branch names count (`fix/thing-ABC-12`).
- Index failures in background runs reach the log; entity lines and dates are escaped;
  `CTX_SOURCES` gets its own index; indexes of other checkouts idle for 30 days are
  removed; notes without a frontmatter name take their H1; no repeated section titles.

### Release 5 (audit of release 4)

- One index per checkout and Claude projects dir (`index-<hash>.db`): running ctx.py
  from a worktree without the overlays no longer prunes their sources.
- A prompt that names a ticket always gets a brief (`/ticket ABC-12`, a bare key);
  lowercase keys count when `ticket_prefixes` is configured.
- `live` output is framed as third-party data and escaped; the config header lists every
  key; docs give the real hook time (under half a second).

### Release 4 (audit of release 3)

- Pointers to rows of sqlite sources use a stable handle (`ctx.py show voice:<row id>`)
  that survives re-indexing; numeric ids are only for immediate use.
- Candidates are ranked per source before weighting, so a large low-weight source cannot
  crowd out memory or notes; snippets are computed only for returned hits (hook under half a second).
- A partial index run no longer marks the whole index fresh; `live --timeout` caps every
  source; a source whose kind changes, becomes a command, or whose database is deleted
  loses its old documents.

### Release 3 (audit of release 2)

- `live` timeouts escalate to SIGKILL and never wait unbounded; query words cannot become
  flags.
- Roots are canonical (realpath), so config dirs linked to one shared dir share one index
  instead of re-reading everything per account.
- A sqlite source re-enabled after removal, or with a changed `db` or `query`, is read
  again; Jira is offered only when a jira source exists.

### Release 2 (audit of release 1)

- Ticket keys and terms match whole words (PROJ-12 is not PROJ-123); `ticket_prefixes`
  and a deny-list keep UTF-8, SHA-256 or GPT-4 from counting as tickets.
- Indexed titles and snippets cannot open or close tags in the agent's context.
- The hook skips its own session (by id and realpath) and harness notifications, shows
  entity and ticket lines once per session, records only the hits it printed, and prunes
  week-old session state.
- `live` timeouts end the command's whole process group; `CTX_REEXEC` is not inherited;
  `CTX_NO_SPAWN` for tests; `{claude_config}` paths; index lock and source failures are
  reported; docs state what reaches the model.

### Release 1

- **CTX-1 Index.** SQLite FTS5 over `files`, `claude-sessions` and `sqlite` sources,
  incremental by mtime and size, realpath dedup across sources (`priority`), accents
  ignored, chunked by heading.
- **CTX-2 Search.** BM25 times source weight, recency half-life, term coverage, phrase and
  entity boost, 3x for an exact ticket key; one hit per document; `show`, `--since`,
  `--source`, `--json`.
- **CTX-3 Brief and hook.** Entities from the glossary (skills, paths, board, live
  sources), weak tail dropped, three per source, eight per prompt; per-session memory so
  later prompts get only new, sharp pointers; trivial prompts skipped; background refresh
  after 30 minutes; never blocks a prompt.
- **CTX-4 Live sources.** `command` sources run in parallel with timeouts, never indexed.
- **CTX-5 Config layering.** Kit defaults, overlay files, user file; `extend`, `enabled`,
  `skip_prompts`, `downweight_sections`.
- **CTX-6 Method.** Rule `context-recon-first` (depth per task) and skill `context-recon`
  (sources, queries, deep-recon subagent brief).
