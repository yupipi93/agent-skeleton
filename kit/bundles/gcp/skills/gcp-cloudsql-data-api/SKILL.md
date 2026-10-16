---
name: gcp-cloudsql-data-api
description: "Run one-off SQL on private-IP Cloud SQL instances through the Cloud SQL Data API (gcloud sql instances execute-sql), with no bastion, proxy or job. Covers enabling it, IAM, password secrets, limits and audit. Use for ad hoc SELECTs, admin fixes or bootstraps. Mutations need approval."
---

# Cloud SQL Data API: one-off queries on private instances

Instances with only a private IP (Private Services Access, no public IP, no bastion)
cannot be reached with `psql` or the Cloud SQL Auth Proxy from a laptop. The **Cloud
SQL Data API** runs SQL through the Cloud SQL Admin control plane
(`gcloud sql instances execute-sql`) and supports exactly that topology: no VPC
connector, no Cloud Run job, no bastion.

Use it for **single ad hoc statements** (diagnosis, a data fix, an admin bootstrap).
For scheduled or bulk migrations, run a migration job (Cloud Run job with the Cloud
SQL connection) instead.

## Safety gate

Rule `database-mutation-requires-approval` applies in full: read-only `SELECT` is
free; any `INSERT`, `UPDATE`, `DELETE` or DDL needs the exact statement, instance,
database and environment shown to the user and an explicit yes, every time. Report
the real result afterwards.

## Enable it on an instance (once, with approval)

The Data API is **off by default**. Enabling it opens an admin SQL surface on that
database, so it is a decision per instance, not a convenience.

1. **Preferred: in Terraform**, if your `google` provider version exposes the setting
   on `google_sql_database_instance` (search its docs for `data_api_access`). If the
   instance comes from a shared module, add the passthrough to the module once rather
   than patching per instance.
2. **Fallback: `gcloud`**, out of band from Terraform, only when the module cannot do
   it yet; note it in the PR or ticket so the next plan does not surprise anyone:

```bash
gcloud sql instances patch my-instance --project=my-project-id --data-api-access=ALLOW_DATA_API
```

Both are infrastructure changes: show them and get approval first.

## IAM

The caller needs `cloudsql.instances.executesql` (included in `roles/cloudsql.admin`;
grant a narrower custom role where you can). Check with the account that owns the
project (skill `gcp-identity-routing`).

## Run a query

```bash
gcloud sql instances list --project=my-project-id
gcloud sql databases list --instance=my-instance --project=my-project-id
gcloud sql users list --instance=my-instance --project=my-project-id
```

Built-in database user with its password in Secret Manager:

```bash
gcloud sql instances execute-sql my-instance \
  --project=my-project-id \
  --database=app \
  --user=app-user \
  --password-secret-version=projects/my-project-id/secrets/app-db-password/versions/latest \
  --sql="SELECT id, email, role FROM users WHERE role = 'admin' LIMIT 20" \
  --partial-result-mode=FAIL_PARTIAL_RESULT
```

Find the secret name in the IaC (the secret that feeds the service's database password
variable) or with `gcloud secrets list --project=my-project-id`. A database module that
creates a user does not necessarily inject its password into the service; check both
ends.

IAM database users (when the instance has IAM authentication on) need no password;
check `gcloud sql instances execute-sql --help` for the current flags.

## Failure seen in practice: CMEK-replicated secrets

Secrets with user-managed replication and customer-managed encryption keys can fail
the Data API's secret lookup in confusing ways: the `projects/*/secrets/*` form is
rejected as the wrong format, the `locations/global` form fails with a region
mismatch, and the regional form returns "not found". **Do not try to pass the
password another way**: an unrecognised flag value is echoed back in gcloud's error
output, password included. Treat such instances as not queryable through the Data
API until the flag supports that secret type, and use a migration job instead.

## Limits

| Constraint | Value |
|---|---|
| Request size | 0.5 MB |
| Response size | 10 MB (`--partial-result-mode=ALLOW_PARTIAL_RESULT` truncates instead of failing) |
| Timeout | 30 seconds |
| Concurrent requests per user per instance | 10 |

Re-verify limits and flags against the current Cloud SQL docs if this skill is old:
the Data API is a recent feature and flags move.

## Audit

Cloud Audit Logs record `cloudsql.instances.executeSql` calls (Data Access logs, if
enabled for Cloud SQL), which gives after-the-fact evidence of what ran and when. For
statement-level logging inside Postgres, enable `pgaudit` on the instance: a separate,
opt-in decision per instance.
