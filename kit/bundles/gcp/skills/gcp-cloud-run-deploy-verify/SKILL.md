---
name: gcp-cloud-run-deploy-verify
description: "Verify a Cloud Run deployment (often triggered by a git tag) with read-only gcloud: revision ready and serving, startup probe passed, no fatal startup logs, smoke test, IAM posture. Use when a deploy tag was pushed, a rollout must be confirmed, or a service misbehaves after a deploy."
---

# Cloud Run deploy verification

A pushed tag or a green build is a claim; a ready revision serving traffic with a
clean startup is evidence. Run these checks, all read-only, and report the result in
the format at the end.

## Inputs

- `PROJECT_ID`, `REGION`, `SERVICE` (required)
- `HEALTHCHECK_PATH` (default `/`), `EXPECTED_SHA` (the commit the tag points to, when
  images are tagged by commit)

Use the account that owns the project (skill `gcp-identity-routing`) and batch the
calls of one step into one shell call (rule `permission-prompt-hygiene`).

## 0. Did the build run?

```bash
gcloud builds list --project="${PROJECT_ID}" --region="${REGION}" --limit=5 \
  --format="table(id,status,createTime,substitutions.TAG_NAME,substitutions.SHORT_SHA)"
```

Cloud Build triggers are regional: pass the trigger's region, or `global` for legacy
triggers. A tag that matched no trigger produces no build at all.

## 1. Revision alignment

```bash
gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" \
  --format="yaml(status.latestCreatedRevisionName,status.latestReadyRevisionName,status.conditions,status.traffic)"
```

Pass: `latestCreatedRevisionName == latestReadyRevisionName`, the `Ready` condition is
`True`, and traffic points at the latest revision (or at the tag you expect). If the
created revision is not ready, the rollout failed and traffic stayed on the old one.

Optional image check:

```bash
gcloud run revisions describe "$(gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.latestReadyRevisionName)')" \
  --project="${PROJECT_ID}" --region="${REGION}" --format='value(spec.containers[0].image)'
```

The image tag or digest should match `EXPECTED_SHA` (images are often tagged with the
merge commit, not the branch commit).

## 2. Startup probe

```bash
LATEST_REV="$(gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" \
  --format='value(status.latestCreatedRevisionName)')"
gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${SERVICE}\" AND resource.labels.revision_name=\"${LATEST_REV}\" AND textPayload:\"probe succeeded\"" \
  --project="${PROJECT_ID}" --limit=5 --freshness=1h --format="table(timestamp,severity,textPayload)"
```

Pass: at least one `STARTUP TCP probe succeeded` (or HTTP) entry for the revision.

## 3. Fatal startup patterns

```bash
gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${SERVICE}\" AND resource.labels.revision_name=\"${LATEST_REV}\" AND (severity>=ERROR OR textPayload:\"Container called exit\" OR textPayload:\"HealthCheckContainerError\" OR textPayload:\"failed to start and listen\")" \
  --project="${PROJECT_ID}" --limit=50 --freshness=1h --format="table(timestamp,severity,textPayload)"
```

Fail: fatal startup errors on the active revision.

## 4. Smoke test

Public service:

```bash
URL="$(gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')"
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 30 "${URL}${HEALTHCHECK_PATH:-/}"
```

Pass: 2xx or the service's normal code.

**IAP-protected or authenticated service:** an anonymous curl only proves IAP is on (a
302 or 401). Use skill `gcp-iap-impersonation` and call the service as its real caller.
Never call it with your own user token as proof that the service works.

## 5. IAM posture

```bash
gcloud run services get-iam-policy "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --format="yaml(bindings)"
gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --format="yaml(metadata.annotations)"
```

The ingress setting is the `run.googleapis.com/ingress` annotation.

For services behind IAP or a load balancer: no `allUsers` on `roles/run.invoker`, the
IAP service agent (`service-<project-number>@gcp-sa-iap.iam.gserviceaccount.com`) has
`roles/run.invoker` when IAP fronts Cloud Run directly, and ingress is
`internal-and-cloud-load-balancing` when only the load balancer should reach it.

## Troubleshooting map

| Symptom | Likely cause |
|---|---|
| `HealthCheckContainerError`, startup probe failed | The app did not listen on `$PORT` in time (wrong port, slow start, crash loop) |
| `Container called exit(0)` before the probe passed | The entrypoint exits early (wrong command, a one-shot script) |
| `P1013` (Prisma) or similar URL parse errors | A malformed `DATABASE_URL`, often a Cloud SQL socket path |
| Created revision never becomes ready | Rollout failed: read the revision's conditions and the first error log |
| Secret or permission errors at start | The runtime service account lacks `secretmanager.secretAccessor` or the secret version is a placeholder |
| No build for the tag | The tag pattern does not match the trigger, or the trigger is in another region |

## Report

1. Health summary: ready or not ready.
2. Latest created vs latest ready revision, and where traffic goes.
3. Startup probe signal: found or not found.
4. The top root-cause evidence from logs, quoted briefly.
5. Next actions, in priority order.
