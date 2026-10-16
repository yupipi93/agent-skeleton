---
name: readme-sync
description: Keep README.md and docs/bundles/*.md in sync with the kit after adding, renaming or removing a bundle, skill, slash-command skill or script. Use when such a change lands, or when asked to update the README or document commands.
---

# README sync

The README is the first thing people read; it must match the kit. After any change to
`kit/bundles/`, update the documentation in the same change.

## When to run

- A bundle is added, removed or renamed, or its `default_enabled` changes.
- A skill is added, removed or renamed, or becomes user-invocable
  (`disable-model-invocation: true`).
- A script that users call directly is added, renamed or gets new arguments.

## Steps

1. Get the current truth:

   ```bash
   bin/skeleton list                 # bundles, skills, states
   ls kit/bundles/*/scripts          # user-facing scripts
   ```

2. Update `README.md`:
   - the bundle table (emoji, name, one-line description, default on or off);
   - the slash-command list (user-invocable skills): name, one line, an example;
   - any `bin/skeleton list` sample output, if the change alters it.
3. Update `docs/bundles/<bundle>.md` for the touched bundle: skills, rules, scripts,
   config files, dependencies.
4. Remove entries for things that no longer exist. Do not touch unrelated sections.
5. Check every relative link you wrote points to an existing file.
6. Run `bin/skeleton check`.

## Style

- One line per entry; details belong in the bundle page.
- Same emoji and names as `bundle.toml`.
- Plain ASCII punctuation, no em dash.
