#!/usr/bin/env bash
#
# jira-start-comment-reminder.sh: after_tool hook. When a shell command moved a Jira
# issue to an in-progress status with jira-transition.sh, remind the agent to post the
# board's start comment ("we are on it") once, so the requester knows the ticket is
# being worked.
#
# Usage (rendered by bin/skeleton into each tool's hook config):
#   kit/bundles/jira/scripts/jira-start-comment-reminder.sh --client claude|gemini < event.json
#
# Behaviour:
#   - fires only for `jira-transition.sh <KEY> --to <status>` where the status is not a
#     close (Done, Cancel, Closed, Resolved); --list, --dry-run and --help are ignored;
#   - sends nothing to Jira itself: the comment still goes through jira-comment.py and
#     the text gate (rule outbound-text-safety);
#   - JIRA_START_COMMENT_HOOK=off disables it; never blocks and never fails loudly.
#
# Output: a JSON hookSpecificOutput.additionalContext object for Claude Code
# (PostToolUse) and Gemini CLI (AfterTool), nothing for other tools.

set -u

CLIENT="claude"
while [ $# -gt 0 ]; do
  case "$1" in
    --client) CLIENT="${2:-claude}"; shift; [ $# -gt 0 ] && shift ;;
    --client=*) CLIENT="${1#*=}"; shift ;;
    -h|--help) awk 'NR > 2 && /^#/ { sub(/^# ?/, ""); print; next } NR > 2 { exit }' "$0"; exit 0 ;;
    *) shift ;;
  esac
done

payload="$(cat 2>/dev/null || true)"

case "$CLIENT" in claude|gemini) ;; *) exit 0 ;; esac
[ "${JIRA_START_COMMENT_HOOK:-on}" = "off" ] && exit 0

PAYLOAD="$payload" CLIENT="$CLIENT" python3 -c '
import json, os, re, shlex, sys
try:
    data = json.loads(os.environ.get("PAYLOAD", ""))
except ValueError:
    sys.exit(0)
if not isinstance(data, dict):
    sys.exit(0)
tool_input = data.get("tool_input") or {}
command = tool_input.get("command") if isinstance(tool_input, dict) else None
if not isinstance(command, str) or "jira-transition.sh" not in command:
    sys.exit(0)
try:
    words = shlex.split(command)
except ValueError:
    words = command.split()
found = []
for i, word in enumerate(words):
    if not word.endswith("jira-transition.sh"):
        continue
    args = []
    for w in words[i + 1:]:
        if w in ("&&", "||", ";", "|"):
            break
        args.append(w)
    if any(a in ("--list", "--dry-run", "-h", "--help") for a in args):
        continue
    key = next((a for a in args if re.fullmatch(r"[A-Z][A-Z0-9]{1,9}-[0-9]{1,7}", a)), None)
    status = None
    for j, a in enumerate(args):
        if a == "--to" and j + 1 < len(args):
            status = args[j + 1]
        elif a.startswith("--to="):
            status = a[5:]
    if not key or not status:
        continue
    if re.search(r"done|cancel|clos|resolv|reject|archiv", status, re.I):
        continue
    found.append((key, status))
if not found:
    sys.exit(0)
lines = []
for key, status in found:
    lines.append(
        f"{key} was just moved to \"{status}\". If the transition succeeded and this starts "
        f"the work, post the start comment on {key} now, once: check "
        f"`kit/bundles/jira/scripts/jira-issue.sh {key} --comments` for an earlier one, then "
        f"send the board config [comments.start] template verbatim in the requester language "
        f"with `kit/bundles/jira/scripts/jira-comment.py {key} --comment ...` "
        f"(skill jira-tickets, \"Picking a ticket up\")."
    )
context = "<jira-start-comment>\n" + "\n".join(lines) + "\n</jira-start-comment>"
event = "PostToolUse" if os.environ["CLIENT"] == "claude" else "AfterTool"
print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))
' 2>/dev/null
exit 0
