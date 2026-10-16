---
name: terraform-import-and-state
description: "Adopt existing resources and repair Terraform state safely: import {}, moved and removed blocks, state backups, the random_id keepers replacement trap, drifted workspaces. Use when importing, renaming or moving resources, editing state, or when a plan wants to replace something that exists."
---

# Terraform import and state work

State is the one artifact Terraform cannot regenerate. Every change to it is reviewed in
a plan first and approved by the user like an apply (rule
`terraform-apply-requires-approval`).

## Golden rules

1. **Back up before surgery.** `terraform state pull > state-backup-$(date +%Y%m%d%H%M%S).tfstate`
   in a git-ignored folder (the backup may contain secrets; never commit or paste it).
2. **Declarative over imperative.** Prefer `import {}`, `moved {}` and `removed {}`
   blocks (Terraform >= 1.5 / 1.1 / 1.7) to `terraform import`, `state mv` and
   `state rm`: they show up in `plan`, go through code review and apply atomically.
3. **The success criterion is the plan.** After an import or a move, the plan for those
   addresses must be `No changes` or in-place updates you can explain. Any `-/+` or
   `must be replaced` means the code does not describe the real resource yet: fix the
   code, never apply through it.
4. **Never broad-apply a drifted workspace.** If the full plan shows changes you did
   not cause (someone rebilled, relabelled or resized by hand), apply only your
   addresses with `-target` (skill `terraform-plan-review`), and report the drift.
   A full apply would silently revert other people's changes.

## Adopt an existing resource: `import {}` blocks

```hcl
import {
  to = google_storage_bucket.assets
  id = "my-project-id/my-project-id-assets"   # import id format: see the provider docs
}

resource "google_storage_bucket" "assets" {
  name     = "my-project-id-assets"
  project  = "my-project-id"
  location = "EU"
}
```

```bash
terraform plan -generate-config-out=generated.tf   # optional: draft HCL for blocks without a resource
TF_WORKSPACE=dev terraform plan -out=import.tfplan
terraform show -json import.tfplan | kit/bundles/terraform/scripts/plan-summary.py
```

- Write the resource from `gcloud ... describe --format=json` (or the generated
  config, cleaned up) until the plan shows `1 to import, 0 to add, 0 to change`.
- `for_each` resources: `to = google_secret_manager_secret.app["api-key"]`; import
  blocks also accept `for_each` themselves (Terraform >= 1.7).
- Remove the `import {}` blocks after the apply (they are idempotent, but noise).
- Prefer blocks even when the CLI would do: `terraform import` writes state
  immediately, without a plan, and some module setups (modules with `count`/
  `for_each` keyed on unknown values, providers configured from data sources) make
  it fail or import into the wrong address.

## The `random_id` keepers trap

Many modules derive names from `random_id` (or `random_string`, `random_pet`) with
`keepers`, for example a project id `my-app-pro-3f`. An imported `random_id` has
**no keepers in state**, so the next plan sees the keepers "change" and replaces the
`random_id`: a new suffix, which means a new name and a **replace of the resource you
just imported**.

Recipe:

1. Import the `random_id` with the existing suffix (the import id is the base64url of
   the bytes: `python3 -c "import base64,sys;print(base64.urlsafe_b64encode(bytes.fromhex(sys.argv[1])).decode().rstrip('='))" 3f`).
2. Plan. If it shows the `random_id` replaced only because of keepers, write the
   keepers into state: `terraform state pull`, set
   `resources[].instances[].attributes.keepers` to exactly what the code declares,
   bump `serial`, `terraform state push` (with a backup, after the user approves).
3. Plan again: the `random_id` and the resource must both show no replace.

Wrapping that in a small script per repo is worth it if it happens more than once.

## Rename or move: `moved {}` blocks

```hcl
moved {
  from = google_cloud_run_v2_service.api
  to   = module.api.google_cloud_run_v2_service.this
}
```

The plan shows the move and no destroy. Keep `moved` blocks for at least one release
(other workspaces and branches still have the old address), then delete them. Moving a
resource between **root modules or state files** is not a `moved` job: `removed {}` in
the old root plus `import {}` in the new one.

## Stop managing without destroying: `removed {}`

```hcl
removed {
  from = google_storage_bucket.legacy
  lifecycle { destroy = false }
}
```

Use it instead of `terraform state rm` when a resource moves to another repo or
should be left alone. It shows in the plan as "will no longer be managed".

## Imperative fallbacks (only when blocks cannot express it)

| Need | Command | Notes |
|---|---|---|
| Inspect | `terraform state list`, `terraform state show '<addr>'` | Read-only, free to run |
| Rename in place | `terraform state mv '<from>' '<to>'` | Prefer `moved {}` |
| Forget | `terraform state rm '<addr>'` | Prefer `removed {}` |
| Replace on purpose | `terraform apply -replace='<addr>'` | Plan it first with `plan -replace`; needs approval |
| Stuck lock | `terraform force-unlock <id>` | Only for a lock you created and whose process is gone |

Each of these rewrites shared state: show the exact command and get an explicit yes.

## Drifted workspaces

1. Plan the whole workspace once with `-lock=false` (read-only) to see the baseline.
2. Classify each change: yours, someone else's in-flight work, manual drift, provider
   noise.
3. Apply only yours, targeted. Leave a note (ticket, PR description) listing the drift
   with the owner, so the next person does not apply over it.
4. Do not "clean up" drift unless that is the task; the fix is often in the code
   (adopt the manual change) rather than a revert.

## Gotchas

- `terraform import` needs the provider configured exactly as in a plan (same
  workspace, same variables). Use `TF_WORKSPACE=<ws>`.
- Import ids differ per resource type; the provider docs list the accepted formats
  at the bottom of each resource page.
- Resources with `deletion_protection` or `prevent_destroy` make a bad apply fail; they
  do not make a bad plan right. Read the plan.
- Two worktrees of one repo share remote state: never run state commands in parallel.
