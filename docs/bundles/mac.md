# 🍎 mac

On by default. One skill, `mac-setup`, that explains how to install, check and repair
everything the kit needs on macOS.

- Bootstrap: `bin/install-mac.sh` (`--dry-run`, `--yes`, `--groups`, `--all`,
  `--skip-brew`). It checks the Xcode Command Line Tools, finds or installs Homebrew
  after asking, runs `brew bundle` for the Brewfile groups of the enabled bundles, then
  `bin/skeleton init` and `bin/skeleton doctor`. Idempotent.
- Per-bundle dependencies: the `# group: <bundle>` sections of the [`Brewfile`](../../Brewfile).
- treehouse (git bundle) is installed from its GitHub releases, not Homebrew.
- Logins: `gh auth login`, `gcloud auth login`, `gcloud auth application-default login`.
- Troubleshooting table: in the skill, `kit/bundles/mac/skills/mac-setup/SKILL.md`.
