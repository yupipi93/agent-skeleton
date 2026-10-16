# Getting started

## 1. Install

```bash
git clone https://github.com/<you>/agent-skeleton.git ~/code/agent-skeleton
cd ~/code/agent-skeleton
bin/install-mac.sh --dry-run     # see what would happen
bin/install-mac.sh               # Xcode tools, Homebrew, Brewfile groups, init, doctor
```

On Linux (best effort): install `git`, `python3` (>= 3.11), `curl` and the tools of the
bundles you want with your package manager, then run `bin/skeleton init`. The installer
skips the Xcode and Homebrew steps there and only runs `init` and `doctor`.

`bin/skeleton` needs Python >= 3.11 and nothing else. If your `python3` is older (macOS
ships 3.9), it re-executes itself with the newest `python3.X` it finds.

## 2. Render the workspace

```bash
bin/skeleton init      # generate CLAUDE.md, .claude/, .cursor/, .gemini/, .agents/
bin/skeleton list      # bundles and skills, on or off
bin/skeleton doctor    # dependencies, config files, freshness, tool reminders
```

`doctor` prints one line per check. On a machine where the Jira bundle is on but not set
up yet, it looks like this:

```text
✅ python 3.14.7 (/opt/homebrew/opt/python@3.14/bin/python3.14)
✅ tools: claude, cursor, gemini, antigravity
✅ 🦴 core: git, python3 found
ℹ️  🦴 core: optional, not found: rg
✅ ☁️ gcp: gcloud, python3 found
✅ 🌿 git: git found
✅ 🎫 jira: curl, python3 found
⚠️  🎫 jira: config ~/.config/agent-skeleton/atlassian.env not found (run bin/skeleton setup jira)
✅ 🏗️ terraform: terraform, python3 found
ℹ️  🏗️ terraform: optional, not found: tflint
✅ generated tree is up to date
```

A warning is a to-do, not a failure: run the command it names (here
`bin/skeleton setup jira`), or disable the bundle if you do not need it.

Open the repository folder in your tool (Claude Code, Cursor, Gemini CLI, Antigravity).
Every tool reads `AGENTS.md` plus its own generated files.

**Cursor users:** open Settings > Rules and turn off "Include third-party plugins,
skills and other configs". Otherwise Cursor also loads `.claude/`, so every skill shows
up twice and Claude hooks run inside Cursor. `bin/skeleton doctor` reminds you.

## 3. Make it yours

```bash
cp skeleton.local.example.toml skeleton.local.toml   # optional, enable/disable create it
bin/skeleton enable voice           # a bundle
bin/skeleton disable plan-files     # a single skill
bin/skeleton setup jira             # a bundle's config wizard: jira, voice and google have one
```

Each wizard writes its file under `~/.config/agent-skeleton/` with mode 0600, reads
secrets at a hidden prompt, and asks before it calls the service to check them.

Personal settings never touch the committed files: `skeleton.local.toml`, `local/` and
every generated path are git-ignored. See [customization.md](customization.md).

## 4. Link your repositories

```bash
bin/skeleton projects list          # what is linked, what is available
bin/skeleton projects add my-api    # fuzzy match under [paths] projects_dir (default ~/code)
bin/skeleton projects remove my-api # removes only the symlink
```

Linked projects appear under `projects/` and in `agent-skeleton.code-workspace`, a
multi-root workspace you can open in VS Code or Cursor.

## 5. Write your own skill

```bash
bin/skeleton new-skill core my-skill        # or a private bundle under local/bundles/
$EDITOR kit/bundles/core/skills/my-skill/SKILL.md
bin/skeleton check && bin/skeleton init
```

The `skill-authoring` skill explains what makes a skill trigger reliably.

## Everyday commands

| Command | What it does |
|---|---|
| `bin/skeleton init [--tools claude,cursor] [--check] [--force] [-v]` | Render everything; idempotent |
| `bin/skeleton list [--bundles \| --skills]` | Table of bundles and skills |
| `bin/skeleton enable\|disable <name> [--kind bundle\|skill\|rule\|hook]` | Toggle in `skeleton.local.toml`, then re-render |
| `bin/skeleton doctor` | Check the machine and the generated tree |
| `bin/skeleton check [--strict]` | Lint the kit |
| `bin/skeleton test` | Run the test suite |
| `bin/skeleton setup <bundle>` | Run a bundle's `setup.sh` |
| `bin/skeleton projects add\|remove\|list` | Manage `projects/` symlinks |
| `bin/skeleton new-skill <bundle> <name> [--user-invocable]` | Scaffold a skill |
