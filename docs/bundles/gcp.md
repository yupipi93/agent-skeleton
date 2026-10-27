# ☁️ gcp

On by default. Recipes for Google Cloud work that agents usually get subtly wrong:
identity, IAP, deploy verification, OAuth, private databases and cost reports.

## Skills

| Skill | Use it for |
|---|---|
| `gcp-identity-routing` | Several Google identities on one machine: a project-prefix to account map, `--account` per command, ADC checks for Terraform, never switching the active account silently |
| `gcp-iap-impersonation` | Calling or smoke-testing an IAP-protected service as its real caller (`--impersonate-service-account`, `--include-email`), status-code table, IAP plus app-key pattern |
| `gcp-cloud-run-deploy-verify` | After a deploy tag: build ran, revision ready and serving, startup probe, fatal logs, smoke test, IAM posture, report format |
| `gcp-oauth-client-setup` | Google Auth Platform (branding, audience, scopes, clients), redirect URIs, the client secret in Secret Manager, OAuth behind IAP |
| `gcp-cloudsql-data-api` | One-off SQL on private-IP Cloud SQL with `gcloud sql instances execute-sql`: enabling it, IAM, password secrets, limits, audit |
| `gcp-billing-report` | Executive cost report (HTML and A4 PDF) from a billing CSV with `tools/billing-exec-report`: the five decisions, exit codes, review checklist |

## Rule (always on)

| Rule | In short |
|---|---|
| `database-mutation-requires-approval` | Read-only SQL freely; `INSERT` / `UPDATE` / `DELETE` / DDL on any database only after an explicit yes for that exact statement |

## Script and tool

| Path | Purpose |
|---|---|
| `kit/bundles/gcp/scripts/gcp-account.py` | Resolve the gcloud account for a project id from `GCP_ACCOUNT_MAP` (`~/.config/agent-skeleton/gcp.env` or the environment); an id no glob matches is discovered read-only with gcloud (home organization breaks ties) and learned, `--sync` learns every visible project |
| `tools/billing-exec-report/` | The cost report generator (stdlib Python, TOML or JSON config, synthetic sample in `examples/sample/`, real reports in the git-ignored `reports/`) |

```bash
printf '%s' 'acme-*=work@example.com *=you@example.com' |
  python3 kit/bundles/core/scripts/lib/envfile.py set ~/.config/agent-skeleton/gcp.env GCP_ACCOUNT_MAP
gcloud run services list --project=acme-dev --region=europe-west1 \
  --account="$(kit/bundles/gcp/scripts/gcp-account.py acme-dev)"

python3 tools/billing-exec-report/generate.py \
  --config tools/billing-exec-report/examples/sample/report.toml --pdf
```

## Highlights

- Secrets stay off argv: tokens reach `curl` through `-H @-` on stdin, secret values
  reach `gcloud secrets versions add` through `--data-file=-`.
- The billing report reconciles every figure against the export and fails (exit 3)
  instead of shipping a document that contradicts itself; it checks the PDF page count
  against the document (exit 4).

## Dependencies

`gcloud` (Homebrew cask `google-cloud-sdk`), `python3` (3.11+ for TOML report
configs, or use JSON); optional `curl`, `bq`; Chrome for report PDFs.
