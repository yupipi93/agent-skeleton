# 🏗️ terraform

On by default. Terraform on Google Cloud done the careful way: the agent writes HCL,
validates, plans and explains the plan; **you** approve every apply.

## Skills

| Skill | Use it for |
|---|---|
| `terraform-gcp` | Designing and changing HCL on GCP: work process, response format, pinning, IAM and secret defaults, the handover block |
| `terraform-plan-review` | Reading a plan: destroys and replaces first, force-new attributes on GCP, drift, minimal `-target` sets (shared locals consumed by several providers) |
| `terraform-import-and-state` | `import {}`, `moved {}` and `removed {}` blocks, state backups, the `random_id` keepers replacement trap, drifted workspaces |
| `terraform-yaml-settings` | The settings-per-workspace pattern (`settings/<env>.yaml`, generic `for_each` resources) with a full 1300-line template in `references/` |
| `iac-docs-maintenance` | ADRs, module READMEs (with console deep-link templates), guides and the docs index, in the same PR as the change |

## Rule (always on)

| Rule | In short |
|---|---|
| `terraform-apply-requires-approval` | Plan freely; `apply` / `destroy` and state rewrites only after an explicit yes for that exact plan; never broad-apply a drifted workspace |

## Script

| Script | Purpose |
|---|---|
| `kit/bundles/terraform/scripts/plan-summary.py` | Summarize `terraform show -json` output: counts, destroys and replaces first with the attribute that forced them, imports, moves, drift; `--match REGEX`, `--targets` (copy-paste `-target=` lines), `--fail-on-destroy` (exit 3, for loops and CI) |

```bash
TF_WORKSPACE=dev terraform plan -out=dev.tfplan
terraform show -json dev.tfplan | kit/bundles/terraform/scripts/plan-summary.py --targets
```

## Highlights

- Validate always comes before plan; `TF_WORKSPACE=<env>` instead of `workspace select`
  so a shared checkout is never switched under someone else.
- The GCS backend locks state natively: no Firestore or lock table.
- The handover is always a copy-paste block plus the question "Apply now?".

## Dependencies

`terraform` (Homebrew `hashicorp/tap/terraform`), `python3`; optional `tflint`, `jq`.
