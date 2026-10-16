---
name: gcp-identity-routing
description: "Pick the right Google identity per GCP project when you have several accounts: a project-prefix to account map, --account pinned per command, Terraform ADC checks, never switching the active account silently. Use before gcloud, bq or terraform calls, or on PERMISSION_DENIED with the wrong account."
---

# GCP identity routing

Many engineers carry two or three Google identities: one per employer, client or
organisation. A project usually grants access to only one of them, and a command run
with the wrong active account fails in confusing ways (`PERMISSION_DENIED`, "project
not found", "Failed to impersonate", a 403 on a budget read) that look like missing
grants. Route each command to the right identity explicitly.

## Rules

1. **Pin the account per command.** `gcloud ... --account=<account>` (most commands),
   or `CLOUDSDK_CORE_ACCOUNT=<account> <tool>` for anything that shells out to
   gcloud. Always pass `--project` too.
2. **Never switch the active account silently.** `gcloud config set account`,
   `gcloud auth login`, `gcloud config configurations activate` and
   `gcloud auth application-default login` change state for every terminal and tool
   on the machine. Only with the user's explicit go, and say so.
3. **A wrong-account error is not a missing grant.** Check which account the command
   ran as before asking anyone for a role.
4. **Pinned tools stay pinned.** Tools that name their own identity (a CI service
   account, an MCP server with its own credentials) are fixed by re-authenticating
   that identity, not by repointing them at your current account.

## The routing map

Keep the map in `~/.config/agent-skeleton/gcp.env` (mode 0600), never in the repo:

```bash
printf '%s' 'acme-*=work@example.com client-*=you@example.org *=you@example.com' |
  python3 kit/bundles/core/scripts/lib/envfile.py set ~/.config/agent-skeleton/gcp.env GCP_ACCOUNT_MAP
```

`envfile.py set` creates the file 0600 (directory 0700) and keeps other keys. Entries
are `<glob>=<account>` separated by spaces; the **first** match wins, so specific
patterns go first. An environment variable `GCP_ACCOUNT_MAP` overrides the file. Then:

```bash
kit/bundles/gcp/scripts/gcp-account.py --list
ACCOUNT="$(kit/bundles/gcp/scripts/gcp-account.py my-project-dev)"
gcloud run services list --project=my-project-dev --region=europe-west1 --account="$ACCOUNT"
```

The script only reads the map: it never runs gcloud or changes anything. Exit 1 means
no pattern matches; ask the user which identity owns the project and suggest adding
it to the map.

Template for the user to fill (write it in the reply, not in a kit file):

| Project id pattern | Account | Notes |
|---|---|---|
| `acme-*` | `work@example.com` | employer organisation |
| `client-*` | `you@example.org` | client organisation, read-only |
| `*` | `you@example.com` | personal sandbox |

## Terraform and client libraries use ADC, not the gcloud account

`--account` does not affect Terraform, the Google client libraries or tools built on
them. They read **Application Default Credentials**
(`~/.config/gcloud/application_default_credentials.json`), which belong to whichever
account ran `gcloud auth application-default login` last.

Before a plan against a project of a different identity:

```bash
ADC_TOKEN="$(gcloud auth application-default print-access-token)"
printf 'access_token=%s' "$ADC_TOKEN" | curl -sS -d @- https://oauth2.googleapis.com/tokeninfo |
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("email", "(no email claim)"))'
```

The token travels on stdin, never on argv or in a URL.

Options when ADC belongs to the other identity, in order of preference:

1. **Impersonate a deployer service account** in the provider
   (`impersonate_service_account = "deployer@${var.project_id}.iam.gserviceaccount.com"`)
   or per run with `GOOGLE_IMPERSONATE_SERVICE_ACCOUNT=...`. Your ADC identity needs
   `roles/iam.serviceAccountTokenCreator` on it.
2. **Short-lived access token for one command**:
   `GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token --account="$ACCOUNT")" terraform plan`.
   It expires in about an hour and does not touch ADC.
3. **Re-login ADC** as the other account: only after the user agrees, because it
   affects every tool on the machine.

## gcloud configurations (optional)

One named configuration per identity keeps account, project and region together:

```bash
gcloud config configurations create client --no-activate
gcloud config set account you@example.org --configuration=client
CLOUDSDK_ACTIVE_CONFIG_NAME=client gcloud projects list   # one command, nothing switched
```

## Troubleshooting

| Symptom | Check |
|---|---|
| `PERMISSION_DENIED` on a project you can see in the console | `gcloud ... --account=` the account the console uses |
| "Failed to impersonate" naming an unexpected address | The active account; pin `--account` |
| Terraform 403 while gcloud works | ADC belongs to another identity (section above) |
| Token refresh errors for one account | Re-authenticate that account only: `gcloud auth login <account>` (with the user's go) |
