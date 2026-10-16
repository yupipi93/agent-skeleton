---
name: git-pr-github
description: "Open and manage GitHub pull requests with gh: full body from a file, drafts, reviewers, labels, checks, updates and the merge policy. Use when opening, updating, checking or merging a PR on a github.com repository, or when the user mentions gh or a GitHub PR."
---

# GitHub pull requests

Use `kit/bundles/git/scripts/pr-github.sh`, a thin wrapper over `gh pr create` that
refuses an empty or incomplete body, appends the ticket link, adds default reviewers and
runs the outbound text guard. Everything else is plain `gh`.

## Setup (once)

```bash
gh auth status || gh auth login        # browser flow; token kept by gh, not by the kit
```

Optional defaults in `~/.config/agent-skeleton/atlassian.env` (or the environment):
`PR_DEFAULT_REVIEWERS=alice,bob` (GitHub logins or `org/team`), `JIRA_SITE` for ticket
links.

## Open a PR

1. Push the branch: `git -C "$WT" push -u origin <branch>`.
2. Write the body (`pr-github.sh --template > pr.md`, then fill Summary, Changes,
   Validation, Rollback).
3. Show the title and body to the user if the repo is shared or public (rule
   `outbound-text-safety`).
4. Open it:

```bash
kit/bundles/git/scripts/pr-github.sh -C "$WT" \
  --title "feat(api): add per-key rate limits" --body-file pr.md \
  --ticket PROJ-123 --reviewer alice --label backend [--draft] [--base main]
```

Run with `--dry-run` first to see the exact `gh` command and the final body. Use
`--draft` when CI should run before review, or the work is not finished.

## After opening

| Need | Command |
|---|---|
| CI status | `gh pr checks <n>` (add `--watch` to wait) |
| Details, review state | `gh pr view <n>` |
| Update the body | `gh pr edit <n> --body-file pr.md` (same gate as opening) |
| Add reviewers or labels | `gh pr edit <n> --add-reviewer bob --add-label infra` |
| Ready for review | `gh pr ready <n>` |
| Comments | `gh pr view <n> --comments` |
| Failed job logs | `gh run view <run-id> --log-failed` |

Fix a failing check on the same branch (commit, push); never disable the check.

## Merge policy

- Merge only when the user asks for it, for that PR.
- Required checks green and required approvals present. Never `--admin` to bypass branch
  protection.
- Use the repo's merge method (look at recent merged PRs or the repo settings), for
  example `gh pr merge <n> --squash --delete-branch`.
- After a merge, verify the deploy the repo triggers, if any, and close the loop on the
  ticket (skill `jira-tickets`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `gh: To get started with GitHub CLI, please run: gh auth login` | `gh auth login` |
| `a pull request for branch ... already exists` | `gh pr view --web`, then `gh pr edit` |
| `No commits between main and <branch>` | nothing pushed, or wrong `--base` |
| Reviewer rejected | the login is not a collaborator, or the team slug is wrong (`org/team`) |
| The text guard blocked | reword the secret-shaped text (skill `jira-tickets`, last section) |
