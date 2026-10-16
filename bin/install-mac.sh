#!/bin/bash
#
# install-mac.sh: one-shot macOS bootstrap for agent-skeleton.
#
#   1. checks the Xcode Command Line Tools
#   2. finds (or, after asking, installs) Homebrew
#   3. runs `brew bundle` for the Brewfile groups of the enabled bundles
#   4. runs `bin/skeleton init` and `bin/skeleton doctor`
#
# Idempotent: safe to run again whenever something looks broken.
#
# Usage: bin/install-mac.sh [--dry-run] [--yes] [--groups core,terraform | --all] [--skip-brew]
#
#   --dry-run    print every step, change nothing
#   --yes        do not ask before installing Xcode tools or Homebrew
#   --groups     comma-separated Brewfile groups (default: core + enabled bundles)
#   --all        every Brewfile group
#   --skip-brew  only run bin/skeleton init and doctor
#
# bash 3.2 compatible (the macOS default /bin/bash).

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BREWFILE="$ROOT/Brewfile"
HOMEBREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"

DRY=0
YES=0
ALL=0
SKIP_BREW=0
GROUPS_ARG=""

say()  { printf '%s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
die()  { printf 'install-mac: %s\n' "$*" >&2; exit 1; }

usage() { sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    -n|--dry-run) DRY=1 ;;
    -y|--yes) YES=1 ;;
    --all) ALL=1 ;;
    --skip-brew) SKIP_BREW=1 ;;
    --groups)
      [ $# -ge 2 ] || die "--groups needs a value"
      GROUPS_ARG="$2"; shift ;;
    --groups=*) GROUPS_ARG="${1#*=}" ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
  shift
done

# run CMD...: execute, or only print in dry-run mode.
run() {
  if [ "$DRY" -eq 1 ]; then
    say "  [dry-run] $*"
  else
    "$@"
  fi
}

# confirm QUESTION: yes with --yes; never prompts in dry-run.
confirm() {
  if [ "$YES" -eq 1 ]; then return 0; fi
  if [ "$DRY" -eq 1 ]; then say "  [dry-run] would ask: $1"; return 0; fi
  printf '%s [y/N] ' "$1"
  ans=""
  read -r ans </dev/tty || return 1
  case "$ans" in y|Y|yes|YES) return 0 ;; esac
  return 1
}

find_brew() {
  if command -v brew >/dev/null 2>&1; then command -v brew; return 0; fi
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$b" ]; then say "$b"; return 0; fi
  done
  return 1
}

# find_python: first python3.X >= 3.11 on PATH or in the Homebrew prefixes.
find_python() {
  for name in python3.14 python3.13 python3.12 python3.11 python3; do
    for cand in "$(command -v "$name" 2>/dev/null || true)" "/opt/homebrew/bin/$name" "/usr/local/bin/$name"; do
      [ -n "$cand" ] && [ -x "$cand" ] || continue
      if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        say "$cand"; return 0
      fi
    done
  done
  return 1
}

# brewfile_groups GROUPS: print the Brewfile entries of a comma-separated group list.
brewfile_groups() {
  awk -v groups=",$1," '
    /^# group:/ { g = $3; next }
    /^[[:space:]]*(tap|brew|cask|mas)[[:space:]]/ { if (index(groups, "," g ",")) print; next }
  ' "$BREWFILE"
}

# enabled_groups: core plus every enabled bundle, as a comma list.
enabled_groups() {
  py="$(find_python)" || return 1
  names="$("$py" "$ROOT/bin/skeleton" list --names --enabled)" || return 1
  out="core"
  for n in $names; do
    case ",$out," in *",$n,"*) ;; *) out="$out,$n" ;; esac
  done
  say "$out"
}

bundle_install() {
  groups="$1"
  entries="$(brewfile_groups "$groups")"
  if [ -z "$entries" ]; then
    say "  nothing to install for groups: $groups"
    return 0
  fi
  say "  groups: $groups"
  if [ "$DRY" -eq 1 ]; then
    printf '%s\n' "$entries" | sed 's/^/  [dry-run] would install: /'
    return 0
  fi
  tmp="$(mktemp -t agent-skeleton-brewfile.XXXXXX)"
  printf '%s\n' "$entries" > "$tmp"
  status=0
  "$BREW" bundle --file "$tmp" || status=$?
  rm -f "$tmp"
  return "$status"
}

say "agent-skeleton macOS bootstrap ($ROOT)"
[ "$DRY" -eq 1 ] && say "dry-run: nothing will be changed"

if [ "$(uname -s)" != "Darwin" ]; then
  say "Not macOS: skipping Xcode tools and Homebrew. Install the Brewfile dependencies with your package manager."
  SKIP_BREW=1
fi

if [ "$SKIP_BREW" -eq 0 ]; then
  step "Xcode Command Line Tools"
  if xcode-select -p >/dev/null 2>&1; then
    say "  ok ($(xcode-select -p))"
  else
    say "  missing"
    if confirm "Run 'xcode-select --install' now?"; then
      run xcode-select --install
      if [ "$DRY" -eq 0 ]; then
        say "  Finish the installer dialog, then run bin/install-mac.sh again."
        exit 0
      fi
    else
      die "the Command Line Tools are required (xcode-select --install)"
    fi
  fi

  step "Homebrew"
  if BREW="$(find_brew)"; then
    say "  ok ($BREW)"
  else
    say "  missing. The official installer (https://brew.sh) is:"
    say "    /bin/bash -c \"\$(curl -fsSL $HOMEBREW_INSTALL_URL)\""
    if confirm "Run the Homebrew installer now?"; then
      if [ "$DRY" -eq 0 ]; then
        /bin/bash -c "$(curl -fsSL "$HOMEBREW_INSTALL_URL")"
      else
        say "  [dry-run] /bin/bash -c \"\$(curl -fsSL $HOMEBREW_INSTALL_URL)\""
      fi
    else
      die "Homebrew is required; install it and run this script again"
    fi
    BREW="$(find_brew || true)"
    [ -n "$BREW" ] || BREW="/opt/homebrew/bin/brew"
  fi
  if [ -x "$BREW" ]; then
    eval "$("$BREW" shellenv)"
  fi

  step "Brewfile"
  if [ "$ALL" -eq 1 ]; then
    groups="$(awk '/^# group:/ { printf "%s%s", sep, $3; sep="," }' "$BREWFILE")"
    bundle_install "$groups"
  elif [ -n "$GROUPS_ARG" ]; then
    bundle_install "$GROUPS_ARG"
  else
    if groups="$(enabled_groups)"; then
      bundle_install "$groups"
    else
      say "  Python >= 3.11 not found yet: installing the core group first"
      bundle_install core
      if groups="$(enabled_groups)"; then
        bundle_install "$groups"
      elif [ "$DRY" -eq 1 ]; then
        say "  [dry-run] after core, the enabled bundles' groups would be installed"
      else
        die "Python >= 3.11 still not found after installing core; check your PATH"
      fi
    fi
  fi
fi

step "bin/skeleton init"
if [ "$DRY" -eq 1 ]; then
  if find_python >/dev/null; then
    "$ROOT/bin/skeleton" init --check || true
  fi
  say "  [dry-run] $ROOT/bin/skeleton init"
else
  "$ROOT/bin/skeleton" init
fi

step "bin/skeleton doctor"
if find_python >/dev/null; then
  "$ROOT/bin/skeleton" doctor || true
else
  say "  skipped: Python >= 3.11 not available"
fi

step "Next steps"
say "  - Log in where you need it: gh auth login, gcloud auth login, gcloud auth application-default login"
say "  - Configure bundles that need credentials: bin/skeleton setup <bundle>"
say "  - Toggle bundles: bin/skeleton list, bin/skeleton enable|disable <name>"
