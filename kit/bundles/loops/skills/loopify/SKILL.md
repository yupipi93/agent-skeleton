---
name: loopify
description: "Rewrite a weak or one-shot prompt into a loop spec (discovery, triage, worker, separate verifier, state, human gates, stop conditions) under loops/<slug>/, plus the runnable tick prompt. Use as a slash command with the prompt to transform."
disable-model-invocation: true
---

# Loopify

Turn a vague or one-shot prompt into a real **loop**: a spec that discovers work,
dispatches it, verifies it with a different agent, persists state, and knows when to
stop or hand off to a human.

Read skill `loop-engineering` first and follow it: it holds the spec format, the state
contract and the human gates this command depends on.

## Arguments

Everything after the command name is the prompt to transform (`$ARGUMENTS` in Claude
Code, `{{args}}` in Gemini CLI). With no argument, use the user's previous message; if
that is empty too, ask for the prompt.

```
/loopify keep the PROJ board moving
/loopify fix the failing tests in projects/my-api
/loopify check every 10 minutes whether the dev deploy is healthy
```

## Procedure

1. **Read the source prompt.** Note what it already implies: repo, cadence, ticket,
   tool, done condition. Resolve any ticket key (`[A-Z][A-Z0-9]+-[0-9]+`) by reading
   the ticket, when the jira bundle is on:
   `kit/bundles/jira/scripts/jira-issue.sh PROJ-123` and
   `kit/bundles/jira/scripts/jira-forms.sh PROJ-123`. A loop built on a misread goal
   iterates in the wrong direction.

2. **Decide whether it should be a loop at all.** A single well-scoped edit, an
   exploratory question, or work that needs approval at every step is not a loop. Say
   so, name the reason, and stop. Loopify only work that *recurs*, *arrives over time*
   or *needs retries until verified*.

3. **Diagnose the prompt** against the anti-patterns table in `loop-engineering`, as a
   short list. This "why the prompt was weak" part is the most useful output. Typical
   findings: task disguised as a goal, unverifiable done condition, self-graded work,
   no discovery source, no state, unbounded scope, no escalation path.

4. **Fill gaps from the repo, not from the user.** Infer the target repo under
   `projects/`, the test, lint or plan command that can serve as the verification gate,
   the board query or `git` / CI command for discovery, and the branch convention. Ask
   **at most one** question, and only for something that changes the loop's shape
   (usually the done condition or the repo). Otherwise choose the idiomatic option and
   record the assumption in the spec.

5. **Write the loop** in `loops/<slug>/` (kebab-case from the goal; if the folder
   exists, update it in place):
   - `LOOP.md`: every field of the spec: goal, done when, discovery, triage gate,
     execution and blast radius, verification (a different agent), state path, cadence,
     human gates, stop conditions.
   - `STATE.md`: the three sections (`## Now`, `## Last attempts`,
     `## Waiting for human`), with `## Now` describing iteration 0.

6. **Emit the runnable tick prompt**: a copy-paste block a fresh agent can run with no
   other context: read `STATE.md`, run discovery, triage, spawn the worker (isolated in
   its own worktree when it touches code, skill `git-worktrees`), spawn a separate
   verifier, write `STATE.md`, decide the next action. Below it, the one-liner that arms
   the cadence:
   - Claude Code in session: `/loop 10m <tick prompt or /command>`
   - Claude Code across sessions: a scheduled agent via `/schedule`
   - Cursor: `/loop`, or an Automation
   - Anything else: a cron or CI schedule running the agent CLI non-interactively

7. **Arm it only if asked.** If the source prompt asked for it to run ("start it",
   "every 10 minutes"), arm the cadence and note how to stop it (the task id, the
   schedule name, or the exact PID you started). Otherwise stop at the spec: arming a
   recurring loop spends tokens and is the user's call. Never arm a duplicate of a loop
   that already runs; check first.

## Hard rules

- The verifier is never the worker. If the spec cannot name a distinct checker and the
  evidence it checks, the loop is not finished.
- Every human gate in `loop-engineering` (apply, mutating SQL, outbound text, merges,
  secret rotation) stops the loop and goes to `## Waiting for human`. A loop never
  grants itself an approval a human-driven run would not get.
- Every stop condition is concrete: max iterations, wall clock, or a repeated-failure
  count. No open-ended loops.

## Result line

| Outcome | Line |
|---|---|
| Success | ✅ **\<slug\>** loopified: spec and state in `loops/<slug>/`, cadence \<interval or event\>, verifier \<who\>. |
| Armed | ✅ **\<slug\>** loop armed at \<interval\>: ran once now, next tick in \<time\>. |
| Not a loop | ⚠️ **\<prompt\>** is one-shot (\<reason\>); run it directly instead. |
| Needs one answer | ⚠️ **\<slug\>** spec drafted: needs \<the missing decision\> before it can run unattended. |
| Error | ❌ Loopify failed at \<step\>: \<reason\>. |
