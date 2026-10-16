---
name: loop-engineering
description: "Design loops: small autonomous systems that discover work, dispatch agents, verify with a separate checker, persist state and pick the next action. Use when the user says loop, run until done, keep checking, every N minutes, unattended, autonomous or self-fix, or before arming a recurring run."
---

# Loop engineering

Prompting is "write prompt, read output, write next prompt". A **loop** replaces the
human in that cycle with a system: it **discovers** work, **dispatches** it to agents,
**verifies** the result with a different agent, **persists** state across runs, and
**decides** whether to iterate, stop or hand off to a human.

| Layer | Unit | Solves |
|---|---|---|
| Prompt engineering | one message | what to say this turn |
| Harness engineering | one agent run | the tools, context and skills of that run |
| **Loop engineering** | many runs over time | who prompts the agent, and when it stops |

A loop is a **recursive goal**: a verifiable purpose the system iterates toward until
it is met or a human is needed. Background reading: "Loop Engineering" by Cobus
Greyling, building on Addy Osmani, Peter Steinberger and Boris Cherny ("my job is to
write loops, not prompts").

## The six parts

Five capabilities plus the spine that holds state. A loop without part 6 is a repeated
one-shot; a loop without part 5 grades its own homework.

| # | Part | Purpose | Claude Code | Cursor | Elsewhere |
|---|---|---|---|---|---|
| 1 | **Heartbeat** | makes "I should check X" happen unattended | `/loop 10m <prompt or /command>` (in session; omit the interval to self-pace); scheduled agents with `/schedule` (cron routines that survive the session); `Stop` / `SessionStart` hooks | `/loop` (monitored background shell), Automations, hooks | cron, CI schedules, Gemini CLI or Antigravity run from cron |
| 2 | **Isolation** | parallel agents that never share files | `Agent` tool with `isolation: "worktree"`, or skill `git-worktrees` | skill `git-worktrees` | `git worktree add` |
| 3 | **Skills** | every run starts with the knowledge, not day one | `kit/bundles/<b>/skills/` rendered by `bin/skeleton init` | same | same |
| 4 | **Connectors** | a loop that can only read is a commentator | MCP servers, kit scripts (`kit/bundles/jira/scripts/`, `kit/bundles/git/scripts/`), `gcloud`, `terraform`, `gh` | same | same |
| 5 | **Sub-agents** (maker and checker) | the writer is structurally a poor judge of its own work | `Agent` tool: background `general-purpose` or custom agents; verify with a separate agent or the `code-review` / `security-review` skills | Task subagents, a separate verifier subagent, Bugbot | a second CLI run with stricter instructions |
| 6 | **Memory** (the spine) | nothing above survives a session boundary by itself | `loops/<slug>/STATE.md` (contract below), plus the ticket or board as external state | same | same |

## The loop spec

The artifact a loop is written as: it replaces the prompt. Every field is load-bearing;
an empty field is where an unattended loop fails. Store it as `loops/<slug>/LOOP.md`.

```markdown
# Loop: <slug>

- **Goal**: one verifiable outcome, phrased as a state of the world, not a task.
- **Done when**: a condition a *different* agent can check without trusting the
  worker. If you cannot write this, you do not have a loop yet.
- **Discovery**: where each tick looks for work (board query, `git log`, failing CI
  check, log query, inbox), as the exact command.
- **Triage gate**: the cheap check run every tick. Expensive work (sub-agents,
  worktrees) starts *only* when it says actionable.
- **Execution**: what the worker may do and its blast radius: repo, file scope, branch
  convention, isolation.
- **Verification**: who checks, with which instructions, against which evidence
  (tests, `terraform plan`, lint, a fresh read of the spec). Never the worker.
- **State**: path to `STATE.md` and what each tick writes back.
- **Cadence**: fixed interval, or event-gated wake plus a long fallback heartbeat.
- **Human gates**: actions that stop the loop and wait for a person.
- **Stop conditions**: max iterations, budget, wall clock, repeated failure count.
```

### State file contract

`loops/<slug>/STATE.md` is often the most valuable artifact a loop produces. It answers
three questions, in this order:

```markdown
## Now
<what is being worked on this iteration, and since when>

## Last attempts
<iteration, what was tried, what happened, evidence (PR, plan output, test run)>

## Waiting for human
<empty, or the exact decision or approval needed and why the loop stopped>
```

Append to `## Last attempts`, never rewrite history; one line per iteration; every
entry carries evidence, not a claim. If `## Waiting for human` is not empty, the next
tick reads it and stops instead of retrying.

`loops/` holds personal state: keep it out of a public repository (add `/loops/` to
`.gitignore` in your fork if it is not ignored already).

### Cadence

- **Event-gated beats time-gated.** Wake on a git ref moving, a CI check finishing, a
  file changing, a log line matching, with a long time-based fallback so idle ticks
  cost little.
- **Triage must be cheap.** A 5-minute loop that spawns an implementer and a verifier
  every tick burns a budget before lunch. Tick order is always discovery, triage, and
  only then spawn.
- In session: `/loop` (Claude Code or Cursor). Across sessions: Claude Code scheduled
  agents (`/schedule`), Cursor Automations, CI or cron.
- One loop per purpose, one unique sentinel per loop. Never arm a duplicate: list the
  running loops and background tasks first.

### Maker and checker

The verifier gets the goal, the done condition, the skills and rules that apply, and
the artifact itself, **not** the worker's summary of what it did. Prefer a different
model or a stricter agent definition for the check. "Done" is a claim until confirmed.

## Human gates

An unattended loop inherits every approval rule of a human-driven run. These always
stop the loop and go to `## Waiting for human`:

- `terraform apply` or destroy (rule `terraform-apply-requires-approval`);
- mutating SQL or DDL on any database (rule `database-mutation-requires-approval`);
- text that leaves the machine: ticket comments, descriptions, chat messages, PR
  bodies to external reviewers (rule `outbound-text-safety`);
- merging a PR, force-pushing, deleting infrastructure, rotating secrets, spending
  money.

A loop may freely read, query, `terraform plan`, run tests and linters, branch, commit,
push its own branch, open a draft PR, and write its own `STATE.md`.

## Anti-patterns

| Anti-pattern | Why it breaks | Fix |
|---|---|---|
| Task disguised as a goal ("refactor the module") | nothing to iterate toward, no stop | restate as a checkable end state |
| Unverifiable done ("make it better") | never terminates, or terminates on vibes | a measurable gate: tests green, plan empty, ticket in Done |
| Worker verifies itself | blind to its own mistakes | a separate checker agent |
| Stateless repetition | every tick is day one; work repeats or oscillates | read `STATE.md` at tick start, write it at tick end |
| Unbounded scope | one bad tick touches everything | file and repo scope plus worktree isolation |
| Expensive triage | tokens burned on idle ticks | a cheap discovery query before any spawn |
| No escalation path | retries a human decision forever | human gates plus `## Waiting for human` |
| Two agents, one checkout | merge disaster | one worktree per task |
| Orphaned worktrees or sleepers | leaked slots and background processes | return worktrees after push; track loop task ids or PIDs and stop only those |

## Realities

- **Cost multiplies**: sub-agents times cadence times iterations. Put the budget in the
  stop conditions.
- **Unattended loops make unattended mistakes.** The verifier reduces them; it does not
  remove the obligation to read what landed.
- **Comprehension debt grows faster with good loops.** Shipped by the loop is not the
  same as understood by you.

## When not to loop

A single well-scoped edit, an exploratory question, anything whose done condition is
"the human looks at it", and anything that needs approval at every step (the loop would
be a sleeping gate, not a system). Say so plainly instead of manufacturing a loop.

## Related

- Command `loopify`: rewrites a weak prompt into a loop spec and state file.
- Skill `git-worktrees`: isolation. Skill `git-branch-pr-workflow`: the branch and PR
  shape a loop's execution step follows.
- Claude Code: `/loop`, `/schedule`, the `Agent` tool. Cursor: `/loop`, Automations,
  Task subagents.
