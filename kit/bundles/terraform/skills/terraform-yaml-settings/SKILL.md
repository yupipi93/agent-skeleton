---
name: terraform-yaml-settings
description: "YAML-driven Terraform on GCP: one settings/<env>.yaml per workspace, a locals loader, generic resources generated from settings (Cloud Run, secrets, buckets, SQL), naming, SOPS secrets, with a full template. Use when bootstrapping such a repo or adding settings blocks or .tf files to one."
---

# YAML-driven Terraform settings

In this pattern the HCL is generic and the environments are data: every service,
bucket, secret and database is declared in `settings/<workspace>.yaml`, and `for_each`
over those maps generates the resources. Adding a service is a YAML change reviewed in
a plan, not new HCL.

## When to use

- Bootstrapping a new IaC repo for a GCP platform with dev / pre / pro.
- Adding a service, bucket, secret or database to a repo that already works this way.
- Adding a new generic `.tf` file that reads a new settings block.

**The repo you are in wins.** Copy its existing patterns first and use the template
only to fill gaps. Write and plan; the user approves every apply (rule
`terraform-apply-requires-approval`).

## The pattern in one screen

```
settings/default.yaml   shared base       settings/<ws>.yaml   per-environment overrides
locals.tf               loader + naming   versions.tf / providers.tf   pins, backend, providers
project.<x>.tf          project level: APIs, network, IAM, monitoring
app.<x>.tf              application level: Cloud Run, secrets, builds, buckets
secrets/<env>/<svc>.enc.yaml   SOPS-encrypted values (optional)
docs/                   adr/, architecture/, guides/, modules/ (skill iac-docs-maintenance)
```

```hcl
locals {
  workspace_file = "${path.module}/settings/${terraform.workspace}.yaml"
  defaults       = yamldecode(file("${path.module}/settings/default.yaml"))
  overrides      = fileexists(local.workspace_file) ? yamldecode(file(local.workspace_file)) : {}
  settings       = merge(local.defaults, local.overrides)   # shallow: see gotchas
  prefix         = local.settings.client.name               # e.g. "app"
  is_production  = terraform.workspace == "pro"
}

resource "google_secret_manager_secret" "app" {
  for_each  = { for s in local.app_secrets : s.key => s }
  project   = local.settings.project.id
  secret_id = each.key
  replication {
    user_managed {
      replicas { location = local.settings.region_name }
    }
  }
}
```

```yaml
# settings/dev.yaml
project:
  id: my-project-dev
region_name: europe-west1
app:
  api:
    name: api
    cloudrun:
      min_instances: 0
      max_instances: 2
      ingress: INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER
      secret_env:
        - name: db-password
          var_name: DATABASE_PASSWORD
```

## Rules

- **Generic resources only.** A new need becomes a new optional settings key read with
  `try(each.value.x, <default>)`, not a hand-written resource for one service.
- **Defaults in code, overrides in YAML.** Every optional key has a `try()` default, so
  old settings files keep planning.
- **Stable `for_each` keys** (service names, secret names), never list indexes.
- **Naming is derived**: `<prefix>-<service>-<resource>`; warn the user that names are
  prefixed when they add an entry, and check GCP length limits (service account ids
  are 6 to 30 characters).
- **Secrets**: Terraform creates the secret and a placeholder version with
  `ignore_changes = [secret_data]`; values arrive out of band (Secret Manager, or SOPS
  files decrypted at plan time with a KMS key). Never a value in YAML or HCL.
- **Rationale lives in ADRs**, not in long comments in the settings (skill
  `iac-docs-maintenance`).
- **Renaming a key renames resources.** A changed map key or `name` is a destroy and
  create unless you add `moved {}` blocks (skill `terraform-import-and-state`).

## Template reference

The full template is long, so it lives in
[references/project-template.md](references/project-template.md). Read only what you
need (`rg -n '<keyword>' kit/bundles/terraform/skills/terraform-yaml-settings/references/project-template.md`):

| Need | Section heading | Approx. lines |
|---|---|---|
| Repo layout (`settings/`, `secrets/`, `docs/`, file naming) | PROJECT STRUCTURE | 18-43 |
| `default.yaml` and per-environment files, every key commented | CONFIGURATION FILES EXPLAINED, 1. YAML Configuration Architecture | 44-431 |
| `locals.tf` loader, `versions.tf`, `providers.tf` | 2. CORE TERRAFORM FILES EXPLAINED | 432-574 |
| `project.apis.tf`, `project.network.tf` | Project-Level Resources | 575-703 |
| `app.cloudrun.tf`, `app.secrets.tf` | Application-Level Resources | 704-976 |
| Environments, security, monitoring, state, cost | COMPREHENSIVE BEST PRACTICES | 977-1286 |
| New-repo checklist | IMPLEMENTATION CHECKLIST | 1287-end |

## Gotchas

- `merge()` is **shallow**: an `app:` block in `dev.yaml` replaces the whole `app:`
  block of `default.yaml`. Either repeat what you need per environment or merge
  per block (`merge(try(local.defaults.app, {}), try(local.overrides.app, {}))`).
- Quote values that must stay strings: `version: 1.10` decodes as the number `1.1`,
  and ids with leading zeros lose them.
- `fileexists()` makes a mistyped workspace silently plan with defaults only. Once
  every environment has its file, drop the `fileexists()` guard so a missing file
  fails the plan instead.
- Two workspaces share one backend bucket and lock per workspace; never run two applies
  on the same workspace (from two worktrees, for example).
