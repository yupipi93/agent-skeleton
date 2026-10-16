#!/usr/bin/env bash
#
# repos-sync.sh: pull every git repository under projects/ in parallel (stash local
# changes, pull --rebase, pop the stash). Terraform's .terraform module cache is skipped.
#
# This mutates shared checkouts. That is what a human wants from it, and exactly what an
# agent must not do on its own (rule worktree-for-project-writes). Under an agent
# environment (CLAUDECODE, CURSOR_AGENT, GEMINI_CLI) it refuses unless --i-am-human is
# passed, which an agent may only do when the user explicitly asked for this sync.
# --dry-run is always allowed.
#
# bash 3.2 compatible: no associative arrays, no mapfile.

set -uo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PROJECTS_DIR="$WORKSPACE/projects"
JOBS=""
DRY_RUN=0
HUMAN=0

usage() {
  cat <<EOF
Usage: kit/bundles/git/scripts/repos-sync.sh [--jobs N] [--projects-dir DIR] [--dry-run] [--i-am-human]

Recursively finds Git repositories under projects/ and syncs them in parallel.
Skips any .terraform directory.

Options:
  -j, --jobs N         Maximum concurrent repositories (default: CPU count)
      --projects-dir  Directory to scan instead of projects/
  -n, --dry-run       List the repositories that would be synced, change nothing
      --i-am-human    Run even under an agent environment (only when the user asked)
  -h, --help          Show this help
EOF
}

cpu_count() {
  local n=""
  if command -v nproc >/dev/null 2>&1; then
    n="$(nproc 2>/dev/null)"
  fi
  [ -z "$n" ] && n="$(sysctl -n hw.ncpu 2>/dev/null)"
  [ -z "$n" ] && n="$(getconf _NPROCESSORS_ONLN 2>/dev/null)"
  echo "${n:-4}"
}

is_positive_int() {
  [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -j|--jobs)
      if [ "$#" -lt 2 ] || ! is_positive_int "$2"; then
        echo "❌ --jobs requires a positive integer"
        exit 2
      fi
      JOBS="$2"
      shift 2
      ;;
    --projects-dir)
      if [ "$#" -lt 2 ]; then
        echo "❌ --projects-dir requires a directory"
        exit 2
      fi
      PROJECTS_DIR="$2"
      shift 2
      ;;
    -n|--dry-run)
      DRY_RUN=1
      shift
      ;;
    --i-am-human)
      HUMAN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

if [ "$DRY_RUN" -eq 0 ] && [ "$HUMAN" -eq 0 ] \
   && [ -n "${CLAUDECODE:-}${CURSOR_AGENT:-}${GEMINI_CLI:-}" ]; then
  echo "❌ Refusing to stash/pull/pop shared checkouts from an agent session (rule worktree-for-project-writes)."
  echo "   If the user explicitly asked for this sync, re-run with --i-am-human; to only list repos, use --dry-run."
  exit 3
fi

if [ -z "$JOBS" ]; then
  JOBS="$(cpu_count)"
fi

if [ ! -d "$PROJECTS_DIR" ]; then
  echo "❌ Projects directory not found: $PROJECTS_DIR"
  exit 1
fi

sync_repo() {
  local repo="$1"

  if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "❌ Not inside a git repository"
    return 1
  fi

  local has_changes=false
  local stash_name
  stash_name="repos-sync-stash-$(date +%Y%m%d-%H%M%S)"

  if ! git -C "$repo" diff --quiet \
    || ! git -C "$repo" diff --cached --quiet \
    || [ -n "$(git -C "$repo" ls-files --others --exclude-standard)" ]; then
    has_changes=true
    echo "📦 Stashing local changes..."
    if ! git -C "$repo" stash push -u -m "$stash_name"; then
      echo "❌ Failed to stash local changes"
      return 1
    fi
  fi

  echo "⬇️  Pulling latest changes (rebase)..."
  if ! git -C "$repo" pull --rebase; then
    echo "❌ Pull failed. Resolve rebase conflicts, then run: git stash pop"
    return 1
  fi

  if [ "$has_changes" = true ]; then
    echo "📤 Restoring local changes..."
    if ! git -C "$repo" stash pop; then
      echo "⚠️  Conflicts while restoring changes. Resolve them manually."
      echo "   Your changes are still in the stash. Run: git stash list"
      return 1
    fi
  fi

  echo "✅ Up to date with local changes preserved"
}

repo_label() {
  local repo="$1"
  if [[ "$repo" == "$WORKSPACE/"* ]]; then
    echo "${repo#"$WORKSPACE/"}"
  else
    echo "$repo"
  fi
}

# Every repo once, keyed by its resolved toplevel. find -H follows only the symlinks
# given on its command line (the projects/<name> links), never ones met while walking,
# so links inside a repo (worktrees, loop dirs) are not chased; find -L did.
discover_repos() {
  local marker repo top key entries=()
  local old_nullglob
  old_nullglob="$(shopt -p nullglob)"
  shopt -s nullglob
  entries=("$PROJECTS_DIR"/*)
  eval "$old_nullglob"
  [ "${#entries[@]}" -eq 0 ] && return 0

  while IFS= read -r -d '' marker; do
    repo="$(dirname "$marker")"
    if ! top="$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null)"; then
      continue
    fi
    key="$(cd "$top" 2>/dev/null && pwd -P)"
    printf '%s\t%s\n' "$key" "$repo"
  done < <(
    find -H "${entries[@]}" \
      -type d -name .terraform -prune -o \
      \( -type d -name .git -o -type f -name .git \) -print0 2>/dev/null
  ) | awk -F '\t' '!seen[$1]++ { print $2 }'
}

running_count() {
  local pid count=0
  for pid in ${pids[@]+"${pids[@]}"}; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      count=$((count + 1))
    fi
  done
  echo "$count"
}

wait_for_slot() {
  while [ "$(running_count)" -ge "$JOBS" ]; do
    sleep 0.2
  done
}

repos=()
while IFS= read -r line; do
  [ -n "$line" ] && repos+=("$line")
done < <(discover_repos | sort)

if [ "${#repos[@]}" -eq 0 ]; then
  echo "⚠️ No Git repositories found under $PROJECTS_DIR"
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  for repo in "${repos[@]}"; do
    echo "would sync: $(repo_label "$repo")"
  done
  echo "🔎 Dry run: ${#repos[@]} Git repo(s) under $PROJECTS_DIR, nothing changed."
  exit 0
fi

log_dir="$(mktemp -d)"
trap 'rm -rf "$log_dir"' EXIT

pids=()
logs=()
labels=()

echo "🔎 Found ${#repos[@]} Git repo(s) under $PROJECTS_DIR"
echo "🚀 Syncing with up to $JOBS parallel job(s)..."
echo ""

for i in "${!repos[@]}"; do
  repo="${repos[$i]}"
  label="$(repo_label "$repo")"
  log="$log_dir/$i.log"

  wait_for_slot

  {
    echo "===== $label ====="
    sync_repo "$repo"
  } >"$log" 2>&1 &

  pids+=("$!")
  logs+=("$log")
  labels+=("$label")
done

ok=0
failed=0

for i in "${!pids[@]}"; do
  if wait "${pids[$i]}"; then
    ok=$((ok + 1))
  else
    failed=$((failed + 1))
  fi

  cat "${logs[$i]}"
  echo ""
done

if [ "$failed" -gt 0 ]; then
  echo "❌ Repository sync finished with $failed failure(s), $ok successful."
  exit 1
fi

echo "✅ Repository sync finished successfully for $ok repo(s)."
