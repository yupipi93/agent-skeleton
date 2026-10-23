# 🌿 git

On by default. Branch first, PR after, every write in its own worktree, and pull
requests that always carry a real description, on GitHub or Bitbucket Cloud.

## Skills

| Skill | Use it for |
|---|---|
| `git-conventional-commits` | Commit messages from the diff: types, scopes, breaking changes, footers |
| `git-branch-pr-workflow` | The task loop: worktree, branch naming, commits, host detection, the mandatory PR body |
| `git-pr-github` | `gh` based PRs: drafts, reviewers, labels, `gh pr checks`, updates, merge policy |
| `git-pr-bitbucket` | Bitbucket Cloud PRs through the REST API: token scopes, reviewers by account id, errors |
| `git-bitbucket-access-bootstrap` | Repository, project or workspace access tokens created in a real Chrome (`tools/bitbucket-access-bootstrap`) and stored in GCP Secret Manager without printing them |
| `git-worktrees` | treehouse v3 leases (`get --lease --json -b`), `.worktreeinclude`, safe return, parallel tasks, plain `git worktree` fallback |
| `worktree` | Slash command: `/worktree PROJ-1 \| PROJ-2` runs each task in its own worktree end to end |

## Rule (always on)

| Rule | In short |
|---|---|
| `worktree-for-project-writes` | Write to `projects/<repo>` only from your own worktree and branch; never switch, pull, reset or stash the shared checkout |

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/git/scripts/pr-github.sh` | `gh pr create --body-file` with a section check (Summary, Changes, Validation, Rollback), ticket link, default reviewers, labels, `--draft`, `--dry-run`, `--template` |
| `kit/bundles/git/scripts/pr-bitbucket.sh` | Bitbucket Cloud PR via REST: workspace, repo and branch from the origin remote, reviewers by account id or `{uuid}`, credentials through `curl -K -`, `--dry-run`, `--template` |
| `kit/bundles/git/scripts/repos-sync.sh` | For humans: stash, `pull --rebase` and pop every repo under `projects/` in parallel; refuses to run inside an agent session unless `--i-am-human`; `--dry-run` lists the repos |

Both PR scripts run the core text guard over the title and body and refuse to send on a
match (exit 5). Exit codes: 0 ok, 2 usage, 3 missing tool or credentials, 4 API error.

## Configuration

GitHub needs only `gh auth login`. Everything else is optional and lives in
`~/.config/agent-skeleton/atlassian.env` (mode 0600, written by `bin/skeleton setup jira`)
or the environment:

| Key | Used by | Meaning |
|---|---|---|
| `PR_DEFAULT_REVIEWERS` | both PR scripts | Comma-separated GitHub logins or Bitbucket account ids |
| `JIRA_SITE` | both PR scripts | Turns `--ticket PROJ-123` into a link |
| `BITBUCKET_WORKSPACE` | `pr-bitbucket.sh` | Fallback when the origin remote does not name one |
| `BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN` | `pr-bitbucket.sh` | Atlassian account email (falls back to `JIRA_EMAIL`) and a scoped API token (`read:repository:bitbucket`, `write:pullrequest:bitbucket`) |
| `GIT_HOST` | `git-branch-pr-workflow` | Force `github` or `bitbucket` instead of reading the origin URL |

## Examples

```bash
# A PR body from the scaffold, then a dry run, then the real thing
kit/bundles/git/scripts/pr-github.sh --template > pr.md
kit/bundles/git/scripts/pr-github.sh -C "$WT" --title "fix(auth): stop redirect loop" \
  --body-file pr.md --ticket PROJ-123 --draft --dry-run

# Lease a worktree with its branch in one call (treehouse v3)
cd projects/my-repo
treehouse get --lease --json --lease-holder PROJ-123 -b fix/redirect-loop-PROJ-123
```

## Design notes

- The PR host comes from the origin URL (`github.com` or `bitbucket.org`); `GIT_HOST`
  only overrides it. One less setting for the common case.
- A PR body is a file, never generated: both scripts refuse an empty body or a body
  without the four sections (`--no-section-check` is the explicit escape).
- `repos-sync.sh` mutates shared checkouts, which the worktree rule forbids for agents,
  so it detects `CLAUDECODE`, `CURSOR_AGENT` and `GEMINI_CLI` and refuses.

## Dependencies

`git`; `gh` for GitHub; `curl` and `python3` for Bitbucket; optional
[treehouse](https://github.com/kunchenguid/treehouse) (not in Homebrew; install the
release binary). Without treehouse, the skills use `git worktree`.
