---
description: Before any text leaves the machine (ticket, comment, PR, chat), draft it, secret-scan it, show the exact text and get approval.
apply: always
---

# Outbound text safety

Applies to every write that carries text to another system: Jira issues and comments,
pull request titles and bodies, chat or email messages, wiki pages.

1. **Draft** the text in a file. Keep it to what the reader needs.
2. **Scan** it: `kit/bundles/core/scripts/text-guard.sh --file <draft>` (exit 2 means
   blocked). The jira and PR scripts run the same scan and refuse to send on a match,
   but the scan is a backstop, not the review.
3. **Show** the exact final text and its destination (ticket key, PR, channel) to the
   user and **wait for an explicit approval** of that text. An approval for one text
   or destination does not cover another.
4. **Send** only then, and report the real result (URL, comment id).

Never include a credential, token, key, password, private key or connection string
with credentials. Reference a secret by its name or location, never by its value.

On boards where comments are visible to requesters or customers (`public_comments` in
the board config), comments carry only the outcome and any user-facing link: no PR or
commit links, internal hostnames or IPs, infrastructure detail or how it was solved.
When unsure whether something is safe for that audience, leave it out.

A blocked scan is often a false positive on secret-shaped prose (`token: value`,
`--secret=name`). Reword (space form of flags, a dash instead of a colon, prose instead
of a dense code block) instead of fighting the pattern; see the `jira-tickets` skill.
