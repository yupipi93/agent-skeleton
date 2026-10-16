# Environment patterns

## Workspaces per environment

The most common layout in single-repo GCP projects: one root module, one Terraform
workspace per environment, one settings file per workspace.

```
settings/
├── default.yaml    # optional shared base
├── dev.yaml
├── pre.yaml
└── pro.yaml
```

```hcl
locals {
  settings = yamldecode(file("${path.module}/settings/${terraform.workspace}.yaml"))
}
```

The full pattern (defaults merge, naming locals, settings-driven resources) is in
skill `terraform-yaml-settings`.

Alternatives you will meet, and how to recognise them:

| Layout | Recognise it by | Select the environment with |
|---|---|---|
| Workspaces | `terraform.workspace` in HCL, `terraform workspace list` shows envs | `TF_WORKSPACE=<env> terraform plan` |
| Directory per env | `envs/dev/`, `envs/pro/` each with a backend | `terraform -chdir=envs/<env> plan` |
| tfvars per env | `dev.tfvars`, `pro.tfvars`, a `-backend-config` per env | `terraform plan -var-file=<env>.tfvars` after the matching `init -backend-config` |

Never mix two of them in one repo without a README saying which wins.

## Resource naming

A typical convention, driven by a short prefix in the settings:

```
<prefix>-<service>-<resource>-<env>     e.g. app-api-sa-dev
```

When the repo prefixes names automatically, warn the user when you add a resource so
nobody hard-codes the unprefixed name elsewhere. GCP limits to remember: service
account ids 6 to 30 characters, Cloud Run job and service names 49 characters (and a
derived service account id can overflow first), bucket names globally unique.

## State

- Remote backend in GCS, one bucket per platform (or per environment for strict
  isolation), versioning on, uniform bucket-level access, no public access.
- **The GCS backend locks state natively** with a lock object next to the state file.
  No Firestore, DynamoDB or other lock table is involved.
- Workspaces store their state under `<prefix>/<workspace>.tfstate` in the same
  bucket.
- Share data between root modules with `terraform_remote_state` or, better, with data
  sources on the real resources; never by copying values by hand.
- Never commit local state (`terraform.tfstate*`) or plan files (`*.tfplan`); they can
  contain secrets.

```hcl
terraform {
  required_version = ">= 1.10"
  backend "gcs" {
    bucket = "my-project-id-tfstate"
    prefix = "platform"
  }
  required_providers {
    google      = { source = "hashicorp/google", version = "~> 6.42" }
    google-beta = { source = "hashicorp/google-beta", version = "~> 6.42" }
  }
}
```

Two checkouts (or two worktrees) of the same repo share the remote state: concurrent
`plan` is fine, concurrent `apply` is not.

## Before planning

1. Mandatory parameters are present in the settings for this environment.
2. No name collides with an existing resource (`gcloud ... list --project=...`).
3. Settings files parse: `terraform validate` reports a `yamldecode` or
   `jsondecode` error with the file and line, so run it before anything else.
4. The workspace matches the target environment (`TF_WORKSPACE`, or
   `terraform workspace show`).
5. Your identity can read everything the plan touches (skill `gcp-identity-routing`
   for which account to use).
6. `terraform validate`, then `terraform plan`, then read it (skill
   `terraform-plan-review`).

## After an approved apply

1. Re-run `terraform plan`: it must report no changes. Anything left is drift or a
   provider quirk worth explaining.
2. Check the security-relevant result directly (IAM bindings, ingress, IAP) with
   `gcloud ... describe`, not only the Terraform output.
3. Update the docs in the same branch (skill `iac-docs-maintenance`).
