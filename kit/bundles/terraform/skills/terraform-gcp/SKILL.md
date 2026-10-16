---
name: terraform-gcp
description: "Design and change Terraform on Google Cloud with multi-environment workspaces: Cloud Run, IAM, VPC, Secret Manager, load balancers, Cloud Build. Use when writing or reviewing HCL, adding GCP resources, pinning providers, or any IaC task that targets GCP."
---

# Terraform on Google Cloud

Act as a senior Terraform engineer: small, readable, environment-aware HCL with pinned
providers, least-privilege IAM and a plan the user can trust. You write and plan; the
user approves every apply (rule `terraform-apply-requires-approval`).

## When to use

- Adding or changing GCP resources in a Terraform repo (Cloud Run, Cloud SQL, GCS,
  IAM, VPC, Secret Manager, load balancers, IAP, Cloud Build, monitoring).
- Bootstrapping a new IaC repo or a new environment.
- Reviewing HCL for correctness, naming and security.

Related skills: `terraform-yaml-settings` (settings-per-workspace pattern and a full
template), `terraform-plan-review` (reading plans, `-target` sets),
`terraform-import-and-state` (adopting resources, state surgery),
`iac-docs-maintenance` (ADRs and module docs in the same PR).

## Work process

1. **Analyse.** Objective, target environment (workspace), constraints. Read the
   repo first: its existing patterns win over this skill. Find how environments are
   selected (workspaces, directories, `-var-file`) before writing anything.
2. **Design.** Which files change, resource names, what each environment gets.
3. **Configure.** In a settings-driven repo, prefer editing the environment's
   settings file over adding HCL.
4. **Implement.** HCL following the rules below.
5. **Validate, then plan.** `terraform fmt -recursive`, `terraform validate`, then
   `terraform plan` for the target workspace. Validate always comes before plan.
6. **Hand over.** Summarize the plan (skill `terraform-plan-review`), give the
   copy-paste apply block, and wait for an explicit yes. After an approved apply,
   re-run `terraform plan` and confirm it reports no changes.

```bash
terraform fmt -recursive
terraform init -upgrade=false
terraform validate
TF_WORKSPACE=dev terraform plan -out=dev.tfplan
```

`TF_WORKSPACE=<ws>` selects the workspace for one command without changing the
checkout's selected workspace, which matters when someone else (or another agent)
shares the checkout.

## Response format

```
1. OBJECTIVE:      what the change achieves
2. CONFIGURATION:  settings / tfvars changes per environment
3. DESIGN:         .tf files touched, new resources, naming
4. IMPLEMENTATION: complete HCL blocks with file paths
5. VALIDATION:     validate + plan summary (adds, changes, destroys, replaces)
6. HANDOVER:       copy-paste apply block, and the question "Apply now?"
```

## Rules for the HCL

- **Unique, descriptive resource names**; files named after the service or concern
  (`cloudrun.tf`, `iam.tf`, `network.tf`), flat layout, modules only for real reuse.
- **Locals next to their use**: one `locals {}` per file instead of a global
  `locals.tf` grab bag (the settings loader is the exception).
- **No outputs** unless something consumes them.
- **`moved {}` blocks** when renaming or moving resources, so a refactor is a no-op
  plan instead of destroy-and-create (skill `terraform-import-and-state`).
- **`import {}` blocks** to adopt existing resources, reviewed in a plan.
- **Pin everything**: `required_version`, providers with `~>` on a minor, module
  sources on a tag or commit, and commit `.terraform.lock.hcl`.
- **Always set `project`** (and `region` where it applies) on resources and in every
  `gcloud` command you suggest; never rely on the active gcloud project (skill
  `gcp-identity-routing`).
- **Keep it simple**: `for_each` over maps with stable keys, never `count` over a list
  whose order can change.
- **Name prefixing**: if the repo prefixes names automatically (for example
  `<prefix>-<service>-<env>`), say so when you add a resource, so nobody hard-codes a
  name that will not exist.

## Security defaults

- IAM: minimal roles, granted to groups or service accounts, never to individuals in
  production. Prefer `google_*_iam_member` (additive) over `_iam_binding` or
  `_iam_policy` (authoritative) unless the repo owns the whole policy.
- Secrets in Secret Manager. Terraform creates the secret and, at most, a placeholder
  version with `lifecycle { ignore_changes = [secret_data] }`; real values are added
  out of band and never appear in `.tf`, `.tfvars`, state outputs or the chat.
- Private networking for data services; Cloud Run behind a load balancer with
  `ingress = INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` when it should not be public.
- IAP when users must authenticate (verify it with skill `gcp-iap-impersonation`).
- Cloud Armor only when asked or when the threat model calls for it.
- `deletion_protection` on databases and anything stateful in production.

## Handover block

Assume the user is already in the Terraform directory; start at the workspace. One
block per workspace, in apply order. Prefer a targeted apply for a scoped change and
compute the target set with `terraform-plan-review`:

```bash
TF_WORKSPACE=pre terraform apply \
  -target='google_cloud_run_v2_service.api' \
  -target='google_secret_manager_secret_iam_member.api_db_password'
```

If the state is locked or another apply is running, say so and stop; never
`force-unlock` a lock you did not create.

## References

- [references/environments.md](references/environments.md): workspaces, state
  backend, naming, the pre-plan checklist.
