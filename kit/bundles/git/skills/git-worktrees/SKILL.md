---
name: git-worktrees
description: "Isolated git worktrees for every write to a project repo: treehouse leases (get --lease --json -b), .worktreeinclude, safe return, parallel tasks, plain git worktree fallback. Use before the first edit in a repo under projects/, or when the user says worktree, treehouse or in parallel."
---

# Worktrees for project writes

Every task that writes to a repository under `projects/` runs in its own worktree (rule
`worktree-for-project-writes`): your branch, your working tree, nobody else's HEAD.

Two ways to get one:

| Tool | When | Strengths |
|---|---|---|
| [treehouse](https://github.com/kunchenguid/treehouse) (v3+) | installed (`treehouse -v`) | pooled, reused slots stay warm (`node_modules`, `.terraform`), durable leases, a return that refuses to wipe someone else's slot |
| plain `git worktree` | treehouse missing | nothing to install |

Both share objects, refs, remotes and branches with the main checkout: a commit on a
named branch is visible there immediately.

## 1. Acquire (treehouse)

Agents always use `--lease`: plain `treehouse get` opens an interactive subshell that a
one-command-per-call agent cannot hold. A lease survives with no process inside.

```bash
REPO="$PWD/projects/<repo>"          # the real repository
BRANCH="fix/login-redirect-PROJ-123"
cd "$REPO"
LEASE_JSON="$(treehouse get --lease --json --lease-holder "PROJ-123" -b "$BRANCH")"
WT="$(printf '%s' "$LEASE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["path"])')"
LEASE_ID="$(printf '%s' "$LEASE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["lease_id"])')"
echo "worktree=$WT lease=$LEASE_ID"
```

- Capture the JSON once, then read both fields from it. Running `get` twice leases two
  slots; reading `path` alone loses the lease id you need to return safely.
- Shell state does not persist between tool calls: note `$WT` and `$LEASE_ID` in your
  working notes and re-set them at the top of each command.
- `-b` creates the branch at the acquired commit and **fails if the branch exists**. For
  an existing branch, acquire without `-b`, then `git -C "$WT" switch <branch>`.
- The slot starts at the freshest default branch (it fetches `origin` first), so no
  pull or rebase is needed. `--base <branch>` cuts from another branch; `--no-fetch`
  skips the fetch.
- `--lease-holder` (the ticket key or a short slug) shows in `treehouse status`.
- Tell the user the worktree path.

## 2. Ignored files (.env and friends)

A new slot has no ignored files; a reused slot still has its previous tenant's. A
committed `.worktreeinclude` in the repository lists patterns of ignored files to copy
from the main checkout root at acquire time:

```text
.env
config/local.tfvars
```

`--include-file <path>` replaces it for one acquisition. Adding `.worktreeinclude` is a
repository change: propose it, do not commit it on the side. Without it, copy what the
task needs (`cp "$REPO/.env" "$WT/"`) and run setup steps (`terraform init`, install
dependencies) inside `$WT`.

## 3. Work

Every edit, command and validation uses paths under `$WT`. Run kit scripts from the kit
root and point them at the worktree (`kit/bundles/git/scripts/pr-github.sh -C "$WT"`).
Never edit `projects/<repo>/...` for a task you are doing in a worktree.

## 4. Commit and push

```bash
git -C "$WT" add path/one path/two
git -C "$WT" commit -m "fix(auth): stop redirect loop"
git -C "$WT" push -u origin "$BRANCH"
```

Then open the PR (skill `git-branch-pr-workflow`).

## 5. Return (treehouse)

Only after the work is committed **and pushed**:

```bash
cd "$REPO" && treehouse return --force --if-lease-id "$LEASE_ID" "$WT"
```

- `return` deletes uncommitted tracked and untracked files, with no undo under `--force`.
- `--if-lease-id` is the interlock: if the slot changed hands, it fails before touching
  anything. Never return a slot you did not lease, and never use `return --all`.
- `cd` out of `$WT` first: `return` terminates processes running inside it, your shell
  included.
- A `lease identity does not match` error means your id is stale: check
  `treehouse status --json`; do not bypass it.

## 6. Fallback: plain git worktree

```bash
REPO="$PWD/projects/<repo>"
BRANCH="fix/login-redirect-PROJ-123"
DEFAULT="$(git -C "$REPO" symbolic-ref --short refs/remotes/origin/HEAD | sed 's#^origin/##')"
WT="$HOME/.worktrees/$(basename "$REPO")/$(printf '%s' "$BRANCH" | tr '/' '-')"
git -C "$REPO" fetch origin
git -C "$REPO" worktree add -b "$BRANCH" "$WT" "origin/$DEFAULT"
```

Copy ignored files by hand (section 2). When the branch is pushed:

```bash
git -C "$REPO" worktree remove "$WT"      # refuses when the tree is dirty: good
git -C "$REPO" worktree prune
```

Never pass `--force` to `worktree remove` unless the user agreed to lose what is there.

## Hard rules

1. **A named branch before the first commit.** Commits on a detached HEAD become
   unreachable after a return.
2. **Push before return or remove.**
3. **One branch, one worktree.** Git refuses a branch checked out elsewhere
   (`is already used by worktree at ...`); the main checkout cannot switch to it either.
4. **Infrastructure state is shared.** Two worktrees of one Terraform repo point at the
   same remote state: parallel `plan` is fine, parallel `apply` is not, and every apply
   still needs the user's explicit yes.
5. **Disk grows with the pool.** `treehouse prune` (dry run unless `--yes`) removes idle,
   clean, merged slots. `prune` and `destroy` options that include leased, in-use or
   unmerged slots lose work: never pass them without telling the user what goes.

## Two tasks in parallel

1. Check the tasks touch **disjoint files**. Worktrees remove file contention, not merge
   conflicts; overlapping tasks run one after the other.
2. Lease one slot per task (distinct branches, distinct holders).
3. Give each worker a self-contained brief: the absolute worktree path and "work only
   inside it", its branch, its file scope, the finish sequence (validate, commit, push,
   PR, report path and PR URL), and "do not return the worktree; the coordinator does".
4. When both report done, check each branch is pushed, then return both slots with
   their lease ids.

To hand a slot to a human: `treehouse enter --print-path <name>` (from `treehouse
status`) prints its path without changing pool state.

## Command reference (treehouse v3)

| Command | Purpose |
|---|---|
| `treehouse get --lease --json [-b B] [--lease-holder L] [--base B] [--include-file F]` | Durable, non-interactive acquire |
| `treehouse status [--json]` | Slots, holders, lease ids, processes |
| `treehouse lease <name>` | Lease an existing slot in place |
| `treehouse enter <name> [--print-path]` | Open or print a slot without touching pool state |
| `treehouse return --force --if-lease-id ID <path>` | Release, reset and recycle one slot |
| `treehouse prune [--yes]` | Remove idle, clean, merged slots (dry run by default) |
| `treehouse init` | Write a default `treehouse.toml` |

Pool settings live in `<repo>/treehouse.toml` (safe keys such as `max_trees`) and
`~/.config/treehouse/config.toml` (also `[hooks] post_create = [...]` for warm-up such
as `terraform init`). Creating either is a deliberate change: propose it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `not a git repository` | you are outside the repo; `cd` into `projects/<repo>` |
| no slot handed out | pool at `max_trees`: `treehouse status`, return finished slots |
| `already used by worktree` | hard rule 3: another branch, or find the holder with `git worktree list` |
| work vanished after a return | check `git reflog` and `git branch -a` in the repo before assuming loss |
| `prune` skips: origin unreachable | it will not judge merge state offline; restore the network |
