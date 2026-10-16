---
name: mac-setup
description: Install, check and repair the kit's dependencies on macOS (Xcode tools, Homebrew, Brewfile groups per bundle, treehouse, gcloud and gh logins). Use when setting up a new Mac, when bin/skeleton doctor reports something missing, or when a command is not found.
---

# Mac setup

One script installs what the enabled bundles need, renders the workspace and checks it:

```bash
bin/install-mac.sh --dry-run     # show what would happen, change nothing
bin/install-mac.sh               # asks before installing Homebrew or Xcode tools
bin/install-mac.sh --yes         # no questions (CI or a fresh machine you own)
```

It is idempotent: run it again any time something looks broken.

## What it does

1. Checks the Xcode Command Line Tools (`xcode-select -p`); offers `xcode-select --install`.
2. Finds Homebrew (`/opt/homebrew` on Apple silicon, `/usr/local` on Intel). If missing,
   prints the official installer command from https://brew.sh and runs it only after a yes.
3. Runs `brew bundle` with the `Brewfile` groups of the **enabled** bundles plus `core`.
   Options: `--groups core,terraform` for an explicit list, `--all` for every group.
4. Runs `bin/skeleton init` and `bin/skeleton doctor`.

## Dependencies per bundle

| Bundle | Homebrew | Notes |
|---|---|---|
| core | git, gh, jq, python@3.12, ripgrep | `bin/skeleton` needs Python >= 3.11; macOS ships 3.9 |
| git | (treehouse, see below) | plain `git worktree` works without it |
| jira | none | curl, jq and python3 |
| terraform | hashicorp/tap/terraform | `tflint` optional |
| gcp | google-cloud-sdk (cask) | then log in, see below |
| docs | google-chrome (cask, optional) | headless Chrome for HTML to PDF |
| voice | ffmpeg | text-to-speech engine configured by `bin/skeleton setup voice` |
| dev | shellcheck | for contributors |

`bin/skeleton doctor` lists, per enabled bundle, which commands are missing.

## treehouse (git bundle)

treehouse keeps a pool of ready git worktrees. It is not in Homebrew. Install it from
https://github.com/kunchenguid/treehouse: download the macOS binary from the releases
page and put it on your `PATH` (for example `~/.local/bin`), or build it with the
command shown in the project's README (for a Go toolchain, `go install` with the module
path given there). Check with `treehouse --help`.

## Logins (once per machine)

```bash
gh auth login                                  # GitHub CLI
gcloud auth login                              # gcloud commands as you
gcloud auth application-default login          # ADC, used by Terraform and SDKs
gcloud config set project my-project-id        # optional default project
```

ADC is a single credential per machine: whichever account ran the last
`application-default login` owns it. Check with
`gcloud auth application-default print-access-token >/dev/null && echo ok`.

## Repair and troubleshooting

| Symptom | Fix |
|---|---|
| `bin/skeleton needs Python >= 3.11` | `brew install python@3.12`; make sure `/opt/homebrew/bin` comes before `/usr/bin` in `PATH` |
| `brew: command not found` after installing | `eval "$(/opt/homebrew/bin/brew shellenv)"`, and add that line to `~/.zprofile` |
| A skill or rule does not appear in a tool | `bin/skeleton init`, then restart the tool; `bin/skeleton list` shows if it is on |
| Skills appear twice in Cursor | Cursor Settings > Rules: turn off "Include third-party plugins, skills and other configs" |
| `doctor` warns a config file is too open | `chmod 600 ~/.config/agent-skeleton/<file>` and `chmod 700 ~/.config/agent-skeleton` |
| `xcode-select` errors after a macOS update | `xcode-select --install` again |
| `brew bundle` fails on one formula | `brew doctor`, fix what it reports, re-run `bin/install-mac.sh` |
| Generated files out of date | `bin/skeleton init` (`bin/skeleton init --check` only reports) |

On a managed (corporate) Mac, installs may need an admin elevation tool and some
commands may always ask for permission. Follow the `permission-prompt-hygiene` rule:
batch what prompts, never work around the prompt.
