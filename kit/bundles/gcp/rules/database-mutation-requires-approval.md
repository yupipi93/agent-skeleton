---
description: Never run a mutating database statement (INSERT, UPDATE, DELETE, MERGE, DDL, GRANT) in any environment without the user's explicit approval of that exact statement.
apply: always
---

# Database mutations require approval

**Do not execute a statement that changes data or schema** (`INSERT`, `UPDATE`,
`DELETE`, `MERGE`, `TRUNCATE`, `CREATE`, `ALTER`, `DROP`, `GRANT`, `REVOKE`, or a
migration) **against any database in any environment** unless the user approved that
exact statement in this conversation.

It applies to every route: `psql` / `mysql` / `sqlcmd`, `gcloud sql instances
execute-sql` (skill `gcp-cloudsql-data-api`), `bq query`, Firestore or Redis writes,
ORM consoles, migration tools, and jobs or scripts that run SQL for you.

Free to run without asking: read-only `SELECT` / `EXPLAIN` for diagnosis, listing
instances, databases, users and schemas.

Before a mutation:

1. Show the exact statement, the instance, the database and the environment.
2. Say how many rows it should touch (run the matching `SELECT count(*)` first) and
   how to undo it.
3. Wait for an explicit yes. An approval does not carry over to a different statement,
   database or environment.
4. Run it, then report the real result (rows affected or returned), not just "done".

Changing a database's settings (enabling an API, flags, users, passwords) is an
infrastructure change: it also needs approval, preferably through Terraform.
