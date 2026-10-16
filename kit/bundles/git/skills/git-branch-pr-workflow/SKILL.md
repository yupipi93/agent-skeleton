---
name: git-branch-pr-workflow
description: "Branch before the first edit, PR after: worktree by default, branch naming, commits, then a PR on GitHub or Bitbucket with a full Summary/Changes/Validation/Rollback body. Use when starting any code, config or IaC change, resolving a ticket, fixing a bug or opening a pull request."
---

# Branch first, PR after

For every task that edits code, configuration or infrastructure in a repository:

1. **Before the first edit**: create a branch, in your own worktree.
2. **After the work is validated**: push and open a pull request with a full body.

This applies per target repository (a repo under `projects/`, not this kit itself, unless
the task is a kit change).

## 1. Worktree by default

Use skill `git-worktrees` (rule `worktree-for-project-writes`): lease a worktree with the
branch created in the same call. Only work in the main checkout when the user explicitly
says so for this repo; then never `switch`, `pull`, `reset` or `stash` there without
asking, because that checkout may hold their work.

## 2. Branch name

`<type>/<short-kebab-desc>[-<TICKET-KEY>]`, with the Conventional Commits types:
`feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`.

- `fix/login-redirect-loop-PROJ-123`
- `feat/rate-limit-public-api`

Never commit to the default branch. If you notice you are on it, branch before staging.

## 3. Work and commit

Validate what the repo supports (formatter, linter, tests, `terraform validate` and
`plan`). Commit with skill `git-conventional-commits`, staging explicit paths only.

## 4. Pick the host

Use `GIT_HOST` (`github` or `bitbucket`) when the user or the environment sets it;
otherwise read `git remote get-url origin`:

| Origin contains | Host | Skill and script |
|---|---|---|
| `github.com` | GitHub | `git-pr-github`, `kit/bundles/git/scripts/pr-github.sh` |
| `bitbucket.org` | Bitbucket Cloud | `git-pr-bitbucket`, `kit/bundles/git/scripts/pr-bitbucket.sh` |
| anything else | ask | the host's own CLI or web UI |

## 5. The PR body (mandatory)

Never open a PR with only a title, a bare link, or the host's generated description.
Write the body to a file (`--template` on either script prints this scaffold):

```markdown
## Summary
What changed and why. Link the ticket.

## Changes
- Concrete list of edits

## Validation
- How it was verified (test run, plan summary, manual checks)

## Rollback
- How to revert safely (revert the merge, re-apply the previous version, ...)
```

The PR text leaves the machine, so it passes the outbound text gate (rule
`outbound-text-safety`): no secrets, no internal-only credentials or hosts. Both scripts
re-scan and refuse to send on a match.

## 6. Push and open

```bash
git -C "$WT" push -u origin <branch>
kit/bundles/git/scripts/pr-github.sh -C "$WT" --title "fix(auth): stop redirect loop" \
  --body-file pr.md --ticket PROJ-123 [--draft]
# or
kit/bundles/git/scripts/pr-bitbucket.sh -C "$WT" --title "fix(auth): stop redirect loop" \
  --body-file pr.md --ticket PROJ-123
```

Scripts run from the kit root with `-C` pointing at the worktree. Reviewers default to
`PR_DEFAULT_REVIEWERS`; add the module owner with `--reviewer` when the repo or board
names one. Return the PR URL to the user.

## 7. Release the worktree

Only after the branch is pushed: return or remove the worktree as `git-worktrees`
section 6 describes. The branch and its commits stay in the repository.

## Merging

Do not merge unless the user asks. When asked, follow the host skill's merge policy
(checks green, required approvals, the repo's merge method).
