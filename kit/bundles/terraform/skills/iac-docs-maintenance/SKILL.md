---
name: iac-docs-maintenance
description: "Keep an IaC repo's docs current in the same PR as the change: ADRs (template, numbering, status), module READMEs with console deep links, guides, architecture state and the docs index. Use after finishing Terraform changes, adding a module or service, or when asked to document infrastructure."
---

# IaC documentation maintenance

Docs for infrastructure rot faster than the code because nobody plans them. The rule
is simple: **the docs change in the same branch and PR as the infrastructure change
they describe.** Use this skill at the end of every IaC task, before opening the PR.

## When to use

After any change that:

- makes an infrastructure decision (new pattern, new GCP service, network, security or
  IAM model, refactoring approach);
- adds or changes a module, service, job, database, bucket, secret or load balancer
  route;
- changes how people operate the platform (deploys, secrets, access, rollbacks);
- renames anything that appears in a doc or a console link.

## Docs layout

Use the repo's own layout when it has one. The default this skill assumes:

```
docs/
├── README.md        master index (every doc linked from here)
├── adr/             Architecture Decision Records, immutable, numbered
├── architecture/    current state: resource catalog, network, load balancer, billing
├── guides/          how-to procedures, step by step
├── modules/<name>/  one README per module or service
├── external/        systems outside this repo that it depends on
└── standards/       conventions (naming, tagging, review)
```

Architecture docs say **what is**, guides say **how to**, ADRs say **why**. Never
duplicate: link to the canonical place with a relative path.

## Decision check: write an ADR?

Create `docs/adr/NNNN-short-title.md` when the change adds a pattern, changes how
resources are structured, introduces a GCP service, or changes networking, security
or IAM. `NNNN` is the next number after the highest existing one.

```markdown
# ADR-NNNN: Title

- **Status**: Accepted | Proposed | Superseded by ADR-XXXX
- **Date**: YYYY-MM-DD

## Context
What problem or requirement forced a decision.

## Decision
What was decided, the key technical choices, and the alternatives rejected.

## Affected files
The .tf and settings files created or changed.

## Consequences
Impact on existing infrastructure, trade-offs, migration steps, follow-up work.

## References
Relative links to related ADRs, guides and architecture docs.
```

- **Accepted** once implemented, **Proposed** while pending, **Superseded by
  ADR-XXXX** when a newer ADR replaces it.
- ADRs are immutable once accepted: change a decision with a new ADR that supersedes
  the old one, and only edit the old one's status line.
- In repos that keep rationale out of the code (no inline comments in IaC), the ADR is
  where every "why" goes.

## Module check: update the module README

`docs/modules/<module>/README.md`, sections in this order:

1. **Title and overview**: what the module is and who uses it.
2. **Endpoints per environment**: public URL, API path, IAP on or off, OAuth callback
   and webhook URL patterns, the GCP project per environment.
3. **Console links per environment**: Cloud Build, Cloud Run services and jobs,
   Artifact Registry, data stores, networking, service accounts, secrets, saved log
   queries. Templates: [references/console-urls.md](references/console-urls.md).
4. **Architecture**: a Mermaid diagram of request and data flows (skill
   `docs-mermaid-diagrams`).
5. **Services**: name, runtime, resources, purpose.
6. **Data resources**: Cloud SQL, Memorystore, BigQuery, GCS, queues.
7. **Configuration**: the settings file and key, plus non-obvious bindings.
8. **Secrets**: every secret by name, the env var it feeds, who creates its value.
   Never a value.
9. **Source repository and deploy triggers**: repo, build files, tag patterns.
10. **Deployment checklist**: manual steps before and after the apply (placeholder
    secrets to fill, OAuth clients to create, DNS to delegate).
11. **Related documentation**: relative links to ADRs and guides.

Discover the real names before writing links (some carry random suffixes); all
read-only:

```bash
PROJECT=my-project-dev REGION=europe-west1 MOD=api
gcloud run services list --project="$PROJECT" --region="$REGION" --filter="metadata.name~$MOD" --format="value(metadata.name)"
gcloud run jobs list --project="$PROJECT" --region="$REGION" --filter="metadata.name~$MOD" --format="value(metadata.name)"
gcloud sql instances list --project="$PROJECT" --filter="name~$MOD" --format="value(name)"
gcloud builds triggers list --project="$PROJECT" --region="$REGION" --filter="name~$MOD" --format="value(name,id)"
gcloud artifacts repositories list --project="$PROJECT" --location="$REGION" --format="value(name)"
gcloud iam service-accounts list --project="$PROJECT" --filter="email~$MOD" --format="value(email)"
gcloud secrets list --project="$PROJECT" --filter="name~$MOD" --format="value(name)"
```

Batch them in one shell call (rule `permission-prompt-hygiene`).

## Procedure check: write or update a guide

New or changed procedure: `docs/guides/<topic>-guide.md`. Actionable steps, commands,
configuration examples, how to verify, how to roll back. Rationale goes to the ADR.

## State check: update architecture docs

Resource catalog, load balancer routes, CIDR allocations, budgets: update the file in
`docs/architecture/` so it describes the state after this change.

## Index check

Every new doc is linked from `docs/README.md` (and from `docs/adr/README.md` if the
repo keeps an ADR table).

## Finish

- Relative links only; check that each one resolves.
- No secrets, internal hostnames you would not publish to the whole team, or personal
  data in docs.
- Mention the doc changes in the PR description.
- A plan file turned into docs: use the `docs-plan-to-docs` command.
