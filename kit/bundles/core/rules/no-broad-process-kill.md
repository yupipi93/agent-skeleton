---
description: Never kill processes by name or pattern; stop only the exact PID you started.
apply: always
---

# Never kill processes by a broad pattern

**Do not run `pkill`, `killall` or `kill $(pgrep ...)` with a name or `-f` pattern.**

`-f` matches the full command line of every process of the user, so a short pattern such
as `cat`, `node`, `python` or `sleep` also hits unrelated programs, including endpoint
security agents. Managed security tooling may flag that as tampering and raise an
incident against the machine's owner.

Instead:

1. Stop what you launched by the PID you captured (`$!`), or with the tool's own
   background-task control.
2. To find a process, list first (`pgrep -fl '<very specific string>'`), read the result,
   and kill only the exact PID that is yours.
3. Never signal, inspect or reconfigure security software (endpoint protection, device
   management agents, managed settings). If a task seems to need it, stop and ask.
4. Prefer not needing cleanup: read a background task's output with the file tools instead
   of spawning helper processes.
