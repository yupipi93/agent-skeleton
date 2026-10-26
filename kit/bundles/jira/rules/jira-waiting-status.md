---
description: Move a ticket to the board's waiting status as soon as finishing it depends on someone outside the team, and back when they answer.
apply: always
---

# Waiting on someone else: say so in the ticket status

The moment a ticket can only move forward with something that is not ours (an answer or
a decision from the requester, a merge or review by another team, an access grant, a
vendor), move it to the board's `[transitions] waiting` status. Do it right away, not at
the end of the day: on service desks that status usually pauses the SLA clock.

1. Make sure the ticket says what is awaited and from whom (a question in an earlier
   comment counts). A new comment goes through the outbound text gate as usual.
2. `kit/bundles/jira/scripts/jira-transition.sh PROJ-123 --to "<waiting status>"`.
3. When the answer arrives (comment, merge, grant), move it back to the `start`
   status and carry on. Close with Done only when the work is complete.

Applies to every ticket you touch, also in batch work: when you finish your part of
several tickets, each one goes either to Done (nothing left) or to the waiting status
(something left that is not ours), never left in progress.

The board config (skill `jira-board-config`) names the status. If a board has no
`waiting` key, list its transitions (`jira-transition.sh PROJ-123 --list`); if none fits,
say so to the user instead of picking On Hold or a cancellation.
