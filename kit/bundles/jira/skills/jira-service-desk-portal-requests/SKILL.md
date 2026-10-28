---
name: jira-service-desk-portal-requests
description: "Raise and follow requests in a Jira Service Management customer portal as the person signed in to a dedicated Chrome (tools/jsm-portal-requests): catalog of request types and fields, plan, send. Use to ask another team's support desk for a group, access, licence or account."
---

# Requests to a service desk portal

When the work needs something from another team's Jira Service Management desk (IT,
corporate systems, people, finance), the request must come from the person, as a
customer of that portal, and often from an account that is not the one the API token
belongs to. `tools/jsm-portal-requests` (`jpr`) does it from a real Chrome on a profile
of its own, where that person signed in once; every call carries that session. Tool
reference: `tools/jsm-portal-requests/README.md`.

Not for tickets on a board you work on (create, comment, transition): those go through
skill `jira-tickets`.

## Steps

All commands from the repo root; `jpr` is `tools/jsm-portal-requests/bin/jpr`.

1. **Session.** `jpr status` prints the signed-in account and exits 7 when it is not
   `JPR_EXPECTED_ACCOUNT`. Exit 3 or a wrong account: `jpr stop`, `jpr login`, and ask
   the user to sign in and close the window. Never type a password for them.
2. **Find the request type.** `jpr portals`, `jpr types <portal>`, `jpr show <portal>
   <type>` read the local catalog. Refresh it with `jpr crawl` (REST, every portal the
   account sees) or `jpr crawl --portal <id> --ui` (also opens each category and create
   page and flags Jira forms). A portal is matched by service desk id, project key or
   name; a type by id or name.
3. **Look for an earlier request.** `jpr mine --all` lists what the account already
   raised; `jpr get <KEY>` shows one with its comments. Reuse a previous request's
   wording for the same type.
4. **Plan.** `jpr request <portal> <type> --summary ... --field "<label or id>=<value>"
   [--description-file f.md]` prints every field, converts option labels to ids,
   flags missing required fields and runs the kit text guard. It sends nothing.
5. **Approval.** The text reaches another team: rule `outbound-text-safety` applies.
   Show the plan output and get an explicit yes for that request.
6. **Send.** Same command plus `--yes`. It stops with exit 6 when the account already
   has an open request of that type (pass `--allow-duplicate` only when it is a
   different need), then prints the key and the portal link. Give both to the user.
7. **Follow up.** `jpr get <KEY>`; answer a question with `jpr comment <KEY> --file
   reply.md` (plan), then `--yes` after the user approves that text.

## Field values

| Field type | `--field` value |
|---|---|
| text, paragraph | plain text, or `@file` |
| select, radio, priority | option label (or id), case-insensitive, unique prefix allowed |
| multi-select, checkboxes | `A; B` |
| cascading select | `Parent > Child` |
| user, users | account ids (`id1; id2`) |
| date | `YYYY-MM-DD` |
| anything else | `json:<raw API value>` |

`description` and other paragraph fields are Jira wiki markup on this API (`*bold*`,
`* item`, `[text|https://...]`), not Markdown.

## Gotchas

- **Jira forms (ProForma)** attached to a request type are invisible to the customer
  REST API. `crawl --ui` marks them and `request` refuses those types: raise them in
  the portal by hand, or with the user in the tool's window (`jpr snap --url ...`).
- Attachments are not supported; add them in the portal after the request exists.
- Request types with no category are hidden from the portal menu; the crawl still
  lists them, but they may not open for a customer.
- The catalog lives in `~/.local/share/jsm-portal-requests/catalog/<site>/` (JSON plus
  one Markdown page per portal). Re-crawl when a create call fails with a field error.
