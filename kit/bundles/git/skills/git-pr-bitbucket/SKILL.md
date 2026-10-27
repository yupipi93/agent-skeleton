---
name: git-pr-bitbucket
description: "Open or merge Bitbucket Cloud pull requests through the REST API: full hand-written body, ticket link, reviewers by account id, Atlassian API token. Use when opening or merging a PR on a bitbucket.org repository, or when Bitbucket PR credentials need setting up."
---

# Bitbucket pull requests

`kit/bundles/git/scripts/pr-bitbucket.sh` opens the PR with the body you wrote (never
Bitbucket's generated description), appends the ticket link, adds reviewers and runs the
outbound text guard. Credentials reach curl on stdin, never on the command line.

## Setup (once)

1. Create an Atlassian API token with scopes at
   https://id.atlassian.com/manage-profile/security/api-tokens ("Create API token with
   scopes", app Bitbucket): `read:repository:bitbucket` and
   `write:pullrequest:bitbucket` at least.
2. Run `bin/skeleton setup jira` and answer yes to the Bitbucket question. It writes, in
   `~/.config/agent-skeleton/atlassian.env` (mode 0600):

| Key | Value |
|---|---|
| `BITBUCKET_WORKSPACE` | workspace slug (default when the origin remote does not say) |
| `BITBUCKET_EMAIL` | Atlassian account email (falls back to `JIRA_EMAIL`) |
| `BITBUCKET_API_TOKEN` | the scoped token |
| `PR_DEFAULT_REVIEWERS` | comma-separated account ids or `{uuid}`s |

Authentication is Basic with the **account email** and the token, not the Bitbucket
username. App passwords are deprecated; do not set one up.

## Open a PR

```bash
git -C "$WT" push -u origin <branch>
kit/bundles/git/scripts/pr-bitbucket.sh --template > pr.md      # then fill it
kit/bundles/git/scripts/pr-bitbucket.sh -C "$WT" \
  --title "fix(dns): correct record TTL" --body-file pr.md --ticket PROJ-123 \
  [--reviewer '{a1b2c3d4-...}'] [--dest main] [--no-close-source] [--dry-run]
```

Workspace, repository and source branch come from the worktree's origin remote and
current branch; the destination defaults to origin's HEAD branch. `--dry-run` prints the
endpoint and JSON payload without sending. On success it prints the PR number and URL.

## Reviewers

Bitbucket wants an `account_id` (`557058:...`) or a `{uuid}`, not a display name or email.
Find them on the person's profile (Bitbucket, Personal settings, or the workspace's
member list), or ask the user. If a required reviewer cannot be resolved, open the PR
anyway and tell the user who still has to be added in the web UI.

## Body and safety

Same body as every PR (skill `git-branch-pr-workflow`): Summary, Changes, Validation,
Rollback; the script refuses a body without them unless `--no-section-check`. The title
and body pass `kit/bundles/core/scripts/text-guard.sh`; exit 5 means blocked.

## Troubleshooting

| HTTP | Meaning |
|---|---|
| 401 | wrong email (must be the account email) or token |
| 403 | token lacks `write:pullrequest:bitbucket`, or no write access to the repo |
| 400 `There are no changes to be pulled` | nothing pushed, or wrong `--dest` |
| 400 reviewer errors | an id is wrong, or the author is listed as a reviewer |
| 404 | workspace or repo slug wrong (check `git remote get-url origin`) |

## Merge (only when the user asks)

Merging stays with the user unless they ask for it. Then, after checks and approvals:

```bash
kit/bundles/git/scripts/pr-bitbucket.sh -C "$WT" --merge 42 [--strategy squash] [--dry-run]
```

It reads the PR first: `OPEN` merges, `MERGED` exits 0 (safe to re-run), anything else
exits 4. Without `--strategy` the repository's default merge method applies; the source
branch is closed unless `--no-close-source`. A long merge (HTTP 202) is polled for up to
two minutes. `--message` overrides the merge commit message and passes the text guard.
After it, `git fetch` and confirm the merge commit on the destination branch.
