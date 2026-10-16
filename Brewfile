# Brewfile for agent-skeleton (macOS).
#
# Install everything:            brew bundle --file Brewfile
# Only what your bundles need:   bin/install-mac.sh   (or --groups core,terraform)
#
# Each "# group: <name>" marker starts the entries of one bundle. bin/install-mac.sh
# reads these markers, so keep one marker per bundle and entries below it.
# Commented entries are optional: uncomment them if you want them.

# group: core
brew "git"
brew "gh"           # GitHub CLI: PR helpers and `gh auth login`
brew "jq"           # optional JSON on the command line for humans; no kit script needs it
brew "python@3.12"  # bin/skeleton needs Python >= 3.11 (macOS ships 3.9)
brew "ripgrep"      # rg: fast search, preferred by agents

# group: git
# treehouse (pooled git worktrees) is not in Homebrew. Install it from
# https://github.com/kunchenguid/treehouse (release binary, or `go install`),
# see the mac-setup skill. Plain `git worktree` works as a fallback.

# group: jira
# Uses curl and python3 only (already covered by core and macOS).

# group: terraform
tap "hashicorp/tap"
brew "hashicorp/tap/terraform"
# brew "tflint"     # optional linter

# group: gcp
cask "google-cloud-sdk"   # gcloud, gsutil, bq

# group: docs
# cask "google-chrome"    # optional: headless Chrome renders HTML to PDF

# group: voice
brew "ffmpeg"       # audio conversion for voice notes

# group: google
# Uses python3 only.

# group: loops
# No extra dependencies.

# group: mac
# No extra dependencies.

# group: dev
brew "shellcheck"   # lint for the kit's shell scripts (contributors)
