---
name: gcp-iap-impersonation
description: "Call or smoke-test a service behind Identity-Aware Proxy (Cloud Run, HTTPS load balancer) as its real caller by impersonating that caller's service account, never your own user. Use when curling an IAP endpoint, verifying a deploy behind IAP, or debugging an IAP 302, 401 or 403."
---

# IAP access through service account impersonation

## Core rule

To verify or call a service protected by IAP, **impersonate the service account of
the caller you are reproducing** with `--impersonate-service-account`. Never test with
your own user identity: your user may be on the allowlist (false pass) or absent
(false fail), and neither tells you whether the service's own identity works. An
impersonated ID token is the local equivalent of the metadata-server token the caller
uses in production.

## Prerequisites

- `roles/iam.serviceAccountTokenCreator` for your user on the target service account.
  If the binding is managed in IaC, add it there (or ask the owner); do not fall back
  to your own identity.
- The right gcloud account for the project (skill `gcp-identity-routing`). An error
  `PERMISSION_DENIED: Failed to impersonate` naming the wrong address is an identity
  problem, not a missing grant.

The examples use `PROJECT_ID=my-project-id` and the caller's service account
`SA="app-runtime@${PROJECT_ID}.iam.gserviceaccount.com"`.

```bash
PROJECT_ID=my-project-id
SA="app-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
# only if you may grant it yourself; otherwise request it or add it in IaC
gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --project="$PROJECT_ID" \
  --member="user:you@example.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## Step 1: find the caller's service account

```bash
gcloud run services describe api --project=my-project-id --region=europe-west1 \
  --format='value(spec.template.spec.serviceAccountName)'
```

For a service-to-service call, impersonate the **consumer's** service account, not the
backend's.

## Step 2: find the IAP audience

The ID token's `aud` must equal the OAuth client id of the IAP backend:

```bash
gcloud compute backend-services describe api-backend --global --project=my-project-id \
  --format='value(iap.oauth2ClientId)'
```

For IAP directly on Cloud Run (no load balancer), the audience is the service URL or
the custom audience configured on the service. The audience is not a secret: it is
also the `client_id=` in the unauthenticated 302 redirect to `accounts.google.com`.

## Step 3: mint an impersonated ID token and call

```bash
TOKEN="$(gcloud auth print-identity-token \
  --account=you@example.com \
  --impersonate-service-account="$SA" \
  --audiences="<IAP_OAUTH_CLIENT_ID>" \
  --include-email)"

printf 'Authorization: Bearer %s\n' "$TOKEN" |
  curl -sS -o /dev/null -w '%{http_code}\n' --max-time 30 -H @- \
  "https://api.example.com/healthz"
```

- `--include-email` is **mandatory** for impersonated tokens. Without it the token has
  no usable `email` claim and IAP rejects it with confusing errors (`email claim
  isn't a string`, `Unable to parse JWT`).
- Keep the token in a shell variable and hand it to curl on stdin (`-H @-`, curl
  7.55+), so it never appears in the process list. Never print it, log it or paste it.
- Check the audience if a 401 persists:

```bash
printf '%s' "$TOKEN" | python3 -c 'import base64,json,sys; p=sys.stdin.read().split(".")[1]; print(json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))["aud"])'
```

## Reading the result

| Status | Meaning |
|---|---|
| `302` to accounts.google.com (no token) | IAP is on and healthy; you did not authenticate |
| `200` (or the app's normal code) | The impersonated identity passed IAP and the app accepted it |
| `401` from IAP | Bad or expired token, wrong audience, or missing `--include-email` |
| `403` | Authenticated but not authorized: the service account lacks `roles/iap.httpsResourceAccessor` on that backend (or the app refused it) |
| `000` | Network, DNS or TLS failure: IAP was never reached |

## Two credentials: IAP plus an app key

When a backend sits behind IAP **and** checks its own API key (an LLM gateway, for
example), send the impersonated ID token in `Proxy-Authorization` (IAP consumes and
strips it) and the app key in `Authorization`:

```bash
APP_KEY="$(gcloud secrets versions access latest --secret=app-key --project=my-project-id)"
printf 'Proxy-Authorization: Bearer %s\nAuthorization: Bearer %s\n' "$TOKEN" "$APP_KEY" |
  curl -sS -X POST "https://gateway.example.com/v1/chat/completions" -H @- \
  -H "Content-Type: application/json" \
  -d '{"model":"my-model","messages":[{"role":"user","content":"ping"}]}'
```

Never type the key on the command line or echo it.

## Related

- `gcp-cloud-run-deploy-verify`: post-deploy checks, which use this skill for the
  smoke test of IAP services.
- `gcp-oauth-client-setup`: the OAuth client behind IAP and user-facing sign-in.
