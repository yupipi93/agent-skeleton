# 🔁 loops

On by default. Turn "keep doing this until it is done" into a small system instead of a
hand-held chat: discovery, triage, a worker, a **separate** verifier, durable state, human
gates and concrete stop conditions.

## Skills

| Skill | Use it for |
|---|---|
| `loop-engineering` | The six parts of a loop (heartbeat, isolation, skills, connectors, maker and checker, memory), the loop spec, the `STATE.md` contract, cadence design, human gates, anti-patterns |
| `loopify` | **Command** (`/loopify <prompt>`): diagnose a weak prompt, write `loops/<slug>/LOOP.md` and `STATE.md`, and emit the runnable tick prompt plus the line that arms it |

## Primitives per tool

| Part | Claude Code | Cursor |
|---|---|---|
| Heartbeat | `/loop 10m <prompt>` in session; scheduled agents (`/schedule`) across sessions; hooks | `/loop`, Automations, hooks |
| Isolation | `Agent` tool with `isolation: "worktree"`, skill `git-worktrees` | skill `git-worktrees` |
| Maker and checker | `Agent` tool (a separate verifier agent), `code-review` / `security-review` | Task subagents, Bugbot |
| Memory | `loops/<slug>/STATE.md` | same |

Gemini CLI and Antigravity run loops from cron or CI with the same spec and state file.

## Gates

A loop inherits every approval rule: `terraform apply`, database mutations, outbound
text, merges and secret rotation stop the loop and land in `## Waiting for human`.

## Note

Loop state is personal. Keep `loops/` out of a public repository (add `/loops/` to
`.gitignore` in your fork if it is not ignored already).

## Dependencies

None beyond the tools you already use.
