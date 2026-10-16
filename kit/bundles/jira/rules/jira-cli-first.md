---
description: Use the jira bundle's REST scripts for every Jira operation; reach for an Atlassian MCP server only when no script covers the need.
apply: always
---

# Jira through the scripts first

Read, search, create, comment on, transition and link Jira issues with
`kit/bundles/jira/scripts/` (skill `jira-tickets` has the table), not with an Atlassian
MCP server.

Why:

- An API token sees more than the MCP scopes do: Attached forms are only readable
  through `jira-forms.sh`.
- No interactive OAuth flow that expires mid-session; one config file to fix.
- The scripts encode safe behaviour: the text guard before every write, configured
  assignee and reporter defaults, and no "Done" reached through a cancellation.

If a need has no script (worklogs, bulk edits), say so and ask before falling back to
an MCP server; adding a flag to the script is usually smaller. Jira worklogs are never
written unless the user explicitly asks, with the ticket and amount confirmed.
