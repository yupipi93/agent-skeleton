# 🦴 core

Always on. The workspace conventions, the safety-gate rules every other bundle relies
on, and the shared script library.

## Skills

| Skill | Use it for |
|---|---|
| `workspace-guide` | Where to write skills, rules, hooks, MCP and settings; what is generated |
| `skill-authoring` | Writing skills that trigger reliably; slash-command skills; `check` |
| `plan-files` | Plans as `plans/<topic>.plan.md`; renaming generated plan names |
| `readme-sync` | Keeping `README.md` and these pages in sync with the kit |
| `permission-auto-accept` | AI Auto-Accept extension: install, how its hook answers prompts, the recommended deny-list, audit |

## Rules (always on)

| Rule | In short |
|---|---|
| `agent-safety-gates` | Index of the gates; gates override autonomy; approvals are per action |
| `permission-prompt-hygiene` | Batch prompted commands, never disguise them, write files with the editor tools |
| `no-broad-process-kill` | No `pkill` / `killall` by pattern; stop only the PIDs you started |

## Scripts

| Script | Purpose |
|---|---|
| `kit/bundles/core/scripts/text-guard.sh` | Block outbound text that looks like a secret (`--file`, stdin, `--client`, `--em-dash`); exit 2 on block |
| `kit/bundles/core/scripts/auto-accept-install.sh` | Install the AI Auto-Accept extension in VS Code (Marketplace) and Cursor / Windsurf / VSCodium (Marketplace VSIX); `--editor`, `--dry-run` |
| `kit/bundles/core/scripts/auto-accept-audit.py` | Where the AI Auto-Accept hook is installed, its deny-list, what it answered that the recommended list would not; `--print-settings` prints that list |
| `kit/bundles/core/scripts/lib/envfile.py` | `get` / `set` (value on stdin) / `unset` / `keys` / `check-mode` for KEY=VALUE config files; importable |
| `kit/bundles/core/scripts/lib/secrets.sh` | `secrets_get`, `secrets_require`, `secrets_curl_basic`, `secrets_curl_bearer`, `secrets_curl_header` (curl `-K -`) |
| `kit/bundles/core/scripts/lib/secretscan.py` | The same patterns from Python: `scan(text)` returns a label or `None` |
| `kit/bundles/core/scripts/lib/secret-patterns.txt` | The shared `<label> <regex>` list |

## Dependencies

`git`, `python3` (>= 3.11 for `bin/skeleton`); optional `gh`, `jq`, `rg`.
