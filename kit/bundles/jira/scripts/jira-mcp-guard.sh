#!/usr/bin/env bash
#
# jira-mcp-guard.sh: before_tool hook for Atlassian / Jira MCP servers. Runs the core
# text guard over the tool-call payload, so a secret never reaches a ticket even when
# an agent uses an MCP server instead of the bundle's scripts.
#
# Usage (rendered by bin/skeleton into each tool's hook config):
#   kit/bundles/jira/scripts/jira-mcp-guard.sh --client claude|cursor|gemini|antigravity < event.json
#
# Cursor's beforeMCPExecution fires for every MCP server, so this script filters itself:
# only calls whose tool or server name mentions atlassian, jira or confluence are
# scanned; everything else is allowed untouched. The scan covers the raw payload and
# its decoded JSON strings (an escaped value cannot slip past).
#
# Exit codes: 0 allow, 2 block (reason on stderr, label only, never the matched text).

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$HERE/../../core/scripts/text-guard.sh"
CLIENT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --client) CLIENT="${2:-}"; shift; [ $# -gt 0 ] && shift ;;
    --client=*) CLIENT="${1#*=}"; shift ;;
    -h|--help) awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; exit 0 ;;
    *) shift ;;
  esac
done
set -- ${CLIENT:+--client "$CLIENT"}

payload="$(cat 2>/dev/null || true)"

scan="$(PAYLOAD="$payload" python3 -c '
import json, os, re, sys
raw = os.environ.get("PAYLOAD", "")
try:
    data = json.loads(raw)
except ValueError:
    data = None
names = []
if isinstance(data, dict):
    for k in ("tool_name", "toolName", "server", "server_name", "serverName", "url", "command"):
        v = data.get(k)
        if isinstance(v, str):
            names.append(v)
    tool = data.get("tool")
    if isinstance(tool, dict) and isinstance(tool.get("name"), str):
        names.append(tool["name"])
if data is not None and not re.search(r"atlassian|jira|confluence", " ".join(names), re.I):
    sys.exit(0)
strings = []
def walk(node):
    if isinstance(node, str):
        strings.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)
walk(data)
sys.stdout.write(raw + "\n" + "\n".join(strings))
' 2>/dev/null)"

printf '%s' "$scan" | /bin/bash "$GUARD" "$@"
