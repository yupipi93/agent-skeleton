---
description: Write to a repository under projects/ only from your own worktree on your own branch, never in the shared checkout.
apply: always
---

# Write to project repos only from your own worktree

The checkouts under `projects/` belong to the user, who switches branches, pulls and keeps
uncommitted work there while you work. A commit made in that tree can land on the wrong
branch without any error. So, the moment a task will **write** to one of those repos
(edit a file, create a branch, commit):

1. Get your own worktree first (skill `git-worktrees`): `treehouse get --lease --json -b
   <branch>`, or `git worktree add -b <branch> <path> origin/<default>` as the fallback.
2. Do every edit, validation and git command inside that worktree path.
3. Commit **and push** before returning or removing the worktree: a return discards
   uncommitted and untracked files.
4. One branch per worktree; parallel tasks own disjoint files.
5. Tell the user the worktree path when you create it.

In the shared checkout, even when only reading:

- never run `git switch`, `checkout`, `pull`, `reset`, `stash` or `clean`; read other
  revisions with `git show <rev>:<path>`;
- never stage with `git add -A` or `git add .`; stage the exact paths you wrote.

Read-only work (reading files, `git log`, a plan, an API query) needs no worktree. If you
find you committed to the wrong branch, say so plainly and move the commit to its own
branch before anything else.
