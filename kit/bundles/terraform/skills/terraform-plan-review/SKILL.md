---
name: terraform-plan-review
description: "Read a terraform plan like a reviewer: destroys and replaces first, force-new attributes, drift you did not cause, minimal -target sets (shared locals, several providers), and a copy-paste apply block. Use after any terraform plan, before proposing an apply, or when asked what a plan does."
---

# Terraform plan review

A plan is the only evidence the user gets before an apply. Your job is to turn it into
a short, honest summary, flag anything destructive or unexpected, and hand over the
smallest apply that does the job. You never apply (rule
`terraform-apply-requires-approval`).

## 1. Produce a reviewable plan

```bash
terraform validate
TF_WORKSPACE=dev terraform plan -out=dev.tfplan
terraform show -json dev.tfplan | kit/bundles/terraform/scripts/plan-summary.py
```

`plan-summary.py` prints counts, then destroys and replaces first (with the attribute
that forced each replace), updates, creates, imports, moves and drift. Add `--match
REGEX` to focus on your resources and `--targets` for `-target=` lines. It only reads
JSON; it never runs Terraform. Delete `*.tfplan` files afterwards: they can contain
secrets.

## 2. Read it in order of consequence

1. **Destroy and replace** (`-`, `-/+`, `+/-`, "must be replaced", "forces
   replacement"). Each one needs a reason you can state. A replace of a database,
   bucket, KMS key, secret, project, service account or static IP is a stop sign:
   data, identity or addresses are lost even if the resource comes back.
2. **Drift** ("Objects have changed outside of Terraform"). Someone changed it by
   hand, or another branch was applied. Do not "fix" drift you were not asked to fix.
3. **Updates in place** (`~`). Check that each changed attribute is one you meant to
   change. IAM changes deserve a second look: `_iam_policy` and `_iam_binding` are
   authoritative and can remove members nobody mentioned.
4. **Creates** (`+`). Check names, project, region, and that nothing sensitive
   (public ingress, `allUsers`, a public bucket) slipped in.
5. **Known after apply** on a data source usually means one of its inputs changes in
   this plan; on a resource attribute it is normal.

## 3. Force-new attributes that surprise people on GCP

| Resource | Changing this replaces it |
|---|---|
| Most resources | `name`, `project`, `location` / `region` / `zone` |
| `google_project` | `project_id` (and anything derived from a `random_id` with changed keepers) |
| `google_service_account` | `account_id` (new email, every binding on it breaks) |
| `google_storage_bucket` | `name`, `location` (a storage class change is in place) |
| `google_sql_database_instance` | `name`, `region`, `master_instance_name`; keep `deletion_protection = true` so a bad plan fails instead of deleting |
| `google_compute_subnetwork` | shrinking `ip_cidr_range` (expanding is in place), `network` |
| `google_secret_manager_secret` | `replication` (including adding CMEK), `secret_id` |
| `google_kms_crypto_key` | `name`, `key_ring` (and a destroyed key cannot decrypt old data) |
| `random_id`, `random_password` | any `keepers` change, or keepers missing after an import |

When a replace is unintended, the fix is usually in the code (a `moved {}` block, a
reverted rename, `lifecycle { ignore_changes = [...] }` for an attribute managed
elsewhere), not in the apply flags. See skill `terraform-import-and-state`.

## 4. Minimal `-target` sets

Targeting is for scoped changes in a workspace you cannot apply wholesale (drift, a
shared module, a huge root). Rules:

- **Take addresses from the plan, never guess them.** Plan with your change, then
  `plan-summary.py --match '<your resource prefix>' --targets`.
- **Quote every address** in single quotes: `-target='module.api.google_cloud_run_v2_service.this["web"]'`.
- `-target` pulls in what the target **depends on**, never what **depends on it**.
  If you change a secret and the service that mounts it, target both.
- **One local, many consumers.** When the change is in a shared `locals` value (or a
  settings file) read by several resources, possibly through **several providers**,
  emit a target for every consumer. Example: DNS records defined once in a local and
  rendered by both a Cloud DNS file and a Route 53 file need targets in both:

  ```bash
  terraform plan \
    -target='google_dns_record_set.records_example_com["app.example.com.|A"]' \
    -target='aws_route53_record.records_example_com["app.example.com.|A"]'
  ```

  Find consumers with `rg -n 'local\.<name>' -g '*.tf'`, then confirm with the plan.
- After a targeted apply, a full `terraform plan` must show only the drift that was
  already there. Say so in the handover.

## 5. Hand over

```
Plan for <workspace>: 2 to add, 1 to change, 0 to replace, 0 to destroy.
- + google_secret_manager_secret.api_key (new placeholder secret)
- ~ google_cloud_run_v2_service.api (env API_KEY now from Secret Manager)
Drift not touched: google_storage_bucket.assets labels changed by hand.
```

```bash
TF_WORKSPACE=dev terraform apply \
  -target='google_secret_manager_secret.api_key' \
  -target='google_cloud_run_v2_service.api'
```

Then ask: "Apply now?" and wait. If the plan changed since the user last saw it, show
the new summary again; an approval covers one plan.

## Gotchas

- `terraform plan -detailed-exitcode` exits 2 when there are changes: not an error.
- A plan made with `-lock=false` is fine for reading; an apply never uses it.
- Provider upgrades show as diffs on many resources; separate them from the feature
  change (upgrade in its own PR, plan clean, then the feature).
- Plans against production may read secrets into the plan file. Keep plan files out
  of git and out of chat.
