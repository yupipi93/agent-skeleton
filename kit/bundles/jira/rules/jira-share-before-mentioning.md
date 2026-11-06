---
description: Before telling someone about a ticket, share it with them and give them the link they can open.
apply: always
---

# Share the ticket before you mention it

Whenever you talk to someone about a ticket (a chat message or email, a comment or PR
that names them, a mention in a meeting summary), they must be able to open it:

1. **Share it first**: `kit/bundles/jira/scripts/jira-share.sh PROJ-123 <email or
   accountId> ...` adds them as request participants ("Shared with" in the portal). It
   skips people already sharing it, so it is safe to run every time.
2. **Put the link in the message**: the last line the script prints. On service desks
   that is the customer portal link, which people without a Jira licence can open; never
   send a `/browse/` link to them.
3. Share with everyone you address or mention, not only the main recipient.

Sharing writes no text, so it needs no approval of its own; the message that carries the
link keeps its gate (rule `outbound-text-safety`). A board that is not a service desk
has no participants: then just send its link. If a person has no account the script can
find, say so and ask for the accountId instead of skipping the share.
