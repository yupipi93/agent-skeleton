---
name: gcp-oauth-client-setup
description: "Set up user-facing Google OAuth on GCP in the Google Auth Platform console (formerly the OAuth consent screen): branding, audience, scopes, OAuth client ids, redirect URIs, and the client secret in Secret Manager. Use when adding Sign in with Google or per-user Google API access."
---

# Google OAuth client setup (Google Auth Platform)

Google replaced the single "OAuth consent screen" page with the **Google Auth
Platform** (console, APIs and Services, Google Auth Platform, or
`https://console.cloud.google.com/auth/overview?project=my-project-id`). Its sections:

| Section | Scope | Holds |
|---|---|---|
| **Branding** | project-wide | App name, support email, logo, app domain links, **authorized domains** |
| **Audience** | project-wide | **Internal** or External user type; test users (External only) |
| **Data access** | project-wide | The **scopes** the project may request (non-sensitive, sensitive, restricted) |
| **Clients** | per app | One **OAuth 2.0 client id** per application, with its redirect URIs |
| **Verification centre, Settings** | project-wide | Verification status, advanced OIDC options |

## Key facts

- **Branding, Audience and Data access are shared by every app in the project.** All
  apps show the same consent branding and draw from one registered scope list; only
  the client is per app. Name the branding for the project or organisation.
- **Internal audience means no Google verification** and no "unverified app" screen,
  even for sensitive scopes, but only when the project belongs to the same Google
  Workspace or Cloud Identity organisation as the users. If "Internal" is selectable,
  you qualify. External plus sensitive scopes means verification (slow) unless the app
  stays in Testing.
- **Scopes**: add the narrowest that work (for example
  `https://www.googleapis.com/auth/calendar.events.readonly`). Each app requests its
  own subset at sign-in.
- **The API must be enabled** on the project (Calendar is `calendar-json.googleapis.com`,
  Drive `drive.googleapis.com`, Gmail `gmail.googleapis.com`). Codify it in the IaC
  list of enabled services.

## Steps for a new app

1. **Enable the API** in IaC (`google_project_service`) and plan it.
2. **Audience**: confirm Internal (once per project).
3. **Branding** (once per project): app name, support email, and the app host's
   parent domain under **Authorized domains** (for `app.example.com`, add
   `example.com`).
4. **Data access**: add the scopes the app needs.
5. **Clients**: Create client, type **Web application**, named after the app, with the
   exact **Authorized redirect URIs** (for example
   `https://app.example.com/api/auth/google/callback`). The **client id** is not a
   secret (app environment variable); the **client secret** goes to Secret Manager.

There is no complete Terraform resource for the consent configuration of an external
or internal app, so these steps stay manual; record them in the module README (skill
`iac-docs-maintenance`). `google_iap_client` covers only IAP's own clients.

## Wiring the secret

- Runtime needs `OAUTH_CLIENT_ID` (plain env), `OAUTH_CLIENT_SECRET` (Secret Manager)
  and `OAUTH_REDIRECT_URI` (plain env, must exactly match a registered URI).
- Terraform creates the secret container with a placeholder version and
  `lifecycle { ignore_changes = [secret_data] }`; add the real value out of band,
  from stdin so it never reaches argv or shell history:

```bash
gcloud secrets versions add app-oauth-client-secret --project=my-project-id --data-file=-
# paste the secret, then Ctrl-D
```

- Take the exact secret name from `terraform plan` or `gcloud secrets list`, and grant
  the runtime service account `roles/secretmanager.secretAccessor` on that secret only.
- For background access to user data, use the authorization-code flow with
  `access_type=offline` and `prompt=consent` to obtain a refresh token, and store it
  encrypted per user. The browser token flow avoids a server callback but yields no
  refresh token.

## Behind IAP

The OAuth callback still works behind IAP: the authorization `code` arrives through
the user's own browser redirect, which carries the IAP session cookie, so IAP admits
it. Verify once end to end. If Cloud Armor sits in front, check that LFI or protocol
rules do not false-positive on the callback URL and exclude the offending rule ids.
IAP gives identity, never authorization to Google APIs: reading a user's data always
needs its own OAuth consent (or domain-wide delegation).

## Gotchas

- The redirect URI must match exactly: scheme, host, path, trailing slash.
- Deleting or recreating the consent configuration affects every app in the project.
- Client secrets can be rotated in the client page (add a new secret, deploy, then
  disable the old one); plan the rotation like any secret change.
- New clients can take a few minutes to work; "invalid_client" right after creation is
  usually propagation.
