---
description: Keep permission prompts few and honest - batch prompted commands, never disguise them, write files with the editor tools.
apply: always
---

# Permission prompt hygiene

Each permission prompt costs the user a click and an interruption. Reduce how often
prompts fire, never evade them.

1. **Free work first.** Reads, searches, `git status` / `log` / `diff` and local scripts
   usually do not prompt. Run them on their own before a step that will prompt.
2. **Batch the prompted commands of one step.** When a step needs several read-only cloud
   or network calls (identity check, describes, lists, a plan), put them in one shell call
   so the user approves once with the whole picture.
3. **Never disguise a command to dodge a prompt.** No wrappers, aliases, `env` prefixes,
   `bash -c`, or re-implementations in another language whose purpose is to stop a rule
   from matching. A prompt may be an organisation's security control. The same goes for
   an auto-accept hook (skill `permission-auto-accept`): its deny-list keeps gated and
   policy-forced commands.
4. **Mutating commands stay alone** (apply, push, delete) with their own approval. Never
   bundle them with read-only checks.
5. **Files go through the editor tools** (Write / Edit), not shell redirects or heredocs
   (`cat > file`, `tee`, `>>`). Redirects can prompt outside the working directory and hide
   the content from review. Then run the file in a short, separate shell call.
