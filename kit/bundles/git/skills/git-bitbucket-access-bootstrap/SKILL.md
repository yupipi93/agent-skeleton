---
name: git-bitbucket-access-bootstrap
description: "Create a Bitbucket Cloud repository, project or workspace access token in a real Chrome and store it in GCP Secret Manager of one or more projects (CMEK too) without printing it. Use when CI, a Cloud Build connection, Renovate or a service needs a Bitbucket token, or to rotate or verify one."
---

# Bitbucket access tokens into Secret Manager

Bitbucket has no API that creates access tokens, so `tools/bitbucket-access-bootstrap`
fills the same dialog a person would, in a real Chrome on a profile that belongs only to
the tool, and pipes the token straight into Secret Manager versions. The value never
reaches argv, stdout, logs or the conversation. Tool reference:
`tools/bitbucket-access-bootstrap/README.md`.

## When to use

- A pipeline, Cloud Build repository connection, Renovate job, Cloud Run service or VM
  needs to clone, push or open pull requests on Bitbucket, and the secret lives in GCP.
- Rotating such a token, or checking that the stored one still works.

Not for the user's own Atlassian API token (personal identity, used by
`pr-bitbucket.sh` and the jira scripts): that one is created by the user by hand.

## Pick the kind and scopes

| Kind | Reach | Needs |
|---|---|---|
| `repository` (default) | one repo | admin on the repo |
| `project` | every repo in a project | admin on the project |
| `workspace` | the whole workspace | workspace admin, Premium plan |

| Preset | Scopes | For |
|---|---|---|
| `read` | `repository` | clone, pull, read-only build triggers |
| `admin` | `repository`, `repository:write`, `repository:admin`, `pullrequest`, `pullrequest:write`, `webhook` | a Cloud Build repository connection, and Renovate on the same token |

Renovate opens and updates dependency PRs, so its token needs `pullrequest:write` on
top of `repository:write`; the `admin` preset carries it, so no separate Renovate token
is needed. `--scopes` adds to a preset or replaces it; `bab create --help` lists them.

## Steps

All commands from the repo root; `bab` is `tools/bitbucket-access-bootstrap/bin/bab`.

1. **Once per machine**: `bab install`, then `bab login`. The user signs in to Bitbucket
   in the window that opens (SSO, second factor) and closes it; the agent never types a
   password. `bab status` must say `signed in: True` and show the expected account
   (exit 3: sign in again; exit 7: wrong account). The expected account is
   `BITBUCKET_EMAIL` in `~/.config/agent-skeleton/atlassian.env` unless
   `--expected-account` or `BAB_EXPECTED_ACCOUNT` says otherwise; `create` refuses to act
   as anyone else.
2. **Secret container**: prefer one created by the project's IaC. When the tool must
   create it (`--create-secret`), make it identical to what the IaC declares, or the
   next apply replaces it (replication is ForceNew) and the versions are lost:
   `--secret-locations <region>` for user-managed replication (required under a
   `gcp.resourceLocations` policy) and `--kms-key` for CMEK, either a full
   `projects/.../cryptoKeys/<key>` or `auto:<keyring-glob>/<key>`, looked up in each
   project. Prefix `PROJECT=` to give one project its own key (or none). The tool
   creates the containers before the token, so a refused secret never leaves a token
   behind.
3. **Plan** (read-only, no browser): token, scopes, expiry, and every destination with
   its account and encryption. Repeat `--gcp-project` to store one token in several
   projects.

   ```bash
   bab create --workspace acme --repo web-app --name admin-token --preset admin \
     --expires 2027-10-01 --secret-name web-app-admin-connector-token \
     --gcp-project acme-dev --gcp-project acme-pro --create-secret \
     --secret-locations europe-west1 --kms-key 'acme-dev=auto:*-cmek-europe-west1/secrets-cmek'
   ```

   The gcloud account per project comes from `kit/bundles/gcp/scripts/gcp-account.py`;
   pass `--account` when the map has no match.
4. **First run on a machine or after a Bitbucket redesign**: add `--check-only`. It fills
   the form, writes a snapshot and cancels.
5. **Gate**: show the plan to the user and wait for an explicit yes. Creating a credential
   and writing secret versions are outward-facing; the approval covers that plan only.
6. **Create**: the same command with `--yes`. Expected lines: `token created`,
   `probe OK`, one `store projects/.../versions/N (read back, matches)` per project,
   `stash removed`.
7. `bab stop` when done: while the debugging port is open, any local process could drive
   that browser.

**Rotation**: Bitbucket refuses two tokens with the same name, so create the new one as
`<name>-YYYYMMDD` into the same secret(s), let consumers pick up `latest` (redeploy, or
the next build or job run), then the user revokes the old token in the Bitbucket UI and
disables the old secret versions.

Check a stored token at any time (prints only the HTTP verdict, per project):
`bab verify --workspace acme --repo web-app --gcp-project acme-dev --secret-name web-app-admin-connector-token`.

## Exit codes

| Code | Meaning | Next |
|---|---|---|
| 0 | done, or plan printed | |
| 2 | bad arguments | fix the flags |
| 3 | not signed in or step-up | user runs `bab stop`, `bab login --url <page>` |
| 5 | token created, some project failed to store it | it is in the stash (0600); fix access, `bab push --stash <file> --gcp-project <p> --yes` |
| 6 | a token with that name exists | rotate with a dated name |
| 7 | browser signed in as another account | user signs out and in with the expected one |
| 1 | other failure | read the printed snapshot path |

## Gotchas

- Always pass `--expires` (at most 365 days ahead). Without it the workspace default
  applies, which can be 7 days: the pipeline breaks a week later. Record the date so the
  rotation is planned.
- Bitbucket ticks implied scopes for you: `pullrequest` adds `repository` read,
  `pullrequest:write` adds `repository:write`.
- Never `cat`, `Read` or print a stash file or a secret version. To prove a value, use
  `bab verify`.
- Exit 5 leaves a live token outside Secret Manager for some project: push it or have
  the user revoke it the same day.
- Tokens belong to the repo, project or workspace, not to a person: they survive the
  creator leaving, which is why automation should use them.
