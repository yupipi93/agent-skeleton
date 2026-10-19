#!/usr/bin/env python3
"""Stop hook: a long task, a complex task or a decision ends with a voice summary.

Rendered by `bin/skeleton init` from kit/bundles/voice/hooks.toml for Claude Code (Stop),
Cursor (stop), Gemini CLI (AfterAgent) and Antigravity (Stop), with `--client <tool>`.

A turn qualifies when any of these holds (thresholds from notify.env):
    long      the turn took VOICE_HOOK_LONG_SECONDS or more (default 240)
    complex   VOICE_HOOK_TOOL_CALLS tool calls or more (default 15), or a subagent ran
    decision  a command was sent to the user (notify.sh --code / --code-only), or the
              agent asked the user a question
    a wall    the written reply is VOICE_HOOK_REPLY_CHARS characters or more (default 1200)

A qualifying turn needs a voice-note.py call that really delivered: the call must be in
the transcript and the voice log must show a "sent note" line written during the turn.
A note stored in the local voice hub (the default channel) counts as delivered.
When the log is missing or the turn start is unknown, the hook fails open.

Ways out, on purpose, so the hook can never trap a session:
  * inert until the bundle is set up: no notify.env yet (bin/skeleton setup voice writes
    it), or NOTIFY_CHANNELS=none, or no usable channel in it;
  * the user's message contains the opt-out phrase (VOICE_HOOK_OPTOUT, default "no audio");
  * after three blocks on the same turn it gives up;
  * any parsing problem lets the turn end.

Blocking: Claude Code, Gemini CLI and Antigravity get exit 2 with the reason on stderr;
Cursor gets {"followup_message": ...} on stdout (its stop hook re-prompts the agent).
Python 3.9+, standard library only.
"""

import datetime
import hashlib
import json
import os
import re
import shlex
import sys

MAX_BLOCKS_PER_TURN = 3
VOICE_BASENAME = "voice-note.py"
VOICE_CMD = "kit/bundles/voice/scripts/voice-note.py"
NOT_A_SEND = ("--dry-run", "--plan", "--no-send", "--self-test", "--list-voices", "-h", "--help")
SHELL_TOOLS = ("Bash", "Shell", "run_shell_command", "run_terminal_cmd", "terminal",
               "run_command", "shell")
SUBAGENT_TOOLS = ("Agent", "Task")
QUESTION_TOOLS = ("AskUserQuestion", "ask_user", "ask_followup_question")


def bail(code=0):
    sys.exit(code)


try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib"))
    import notifylib as nl
except Exception:                                             # noqa: BLE001
    sys.exit(0)                    # a broken install must never block a turn


def client_from_argv(argv):
    for i, arg in enumerate(argv):
        if arg == "--client" and i + 1 < len(argv):
            return argv[i + 1].strip().lower()
        if arg.startswith("--client="):
            return arg.split("=", 1)[1].strip().lower()
    return "claude"


def as_int(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------- shell parsing
HEREDOC = re.compile(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")


def strip_heredocs(cmd):
    """Heredoc bodies are data, not commands this turn ran."""
    out, tag = [], None
    for line in cmd.split("\n"):
        if tag is None:
            out.append(line)
            m = HEREDOC.search(line)
            if m:
                tag = m.group(1)
        elif line.strip() == tag:
            tag = None
    return "\n".join(out)


def newlines_to_semicolons(cmd):
    """Outside quotes a newline separates commands; inside one it is content."""
    out, quote, escaped = [], None, False
    for ch in cmd:
        if escaped:
            out.append(ch)
            escaped = False
        elif ch == "\\" and quote != "'":
            out.append(ch)
            escaped = True
        elif quote:
            if ch == quote:
                quote = None
            out.append(ch)
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        else:
            out.append(" ; " if ch == "\n" else ch)
    return "".join(out)


def invocations(command, basename):
    """Token lists of each real invocation of `basename` (not an assignment, not data).

    Tokenise the whole command once, then split the token list on operators: splitting
    the raw text first would cut a multi-paragraph quoted summary in half.
    """
    operators = {";", "|", "||", "&", "&&"}
    text = newlines_to_semicolons(strip_heredocs(command))
    try:
        tokens = shlex.split(text)
    except ValueError:
        # Unbalanced quoting: fail open, a mention of the script counts as a call.
        return [[basename]] if basename in text else []
    found, current = [], None
    for t in tokens:
        if "=" not in t and t.rsplit("/", 1)[-1] == basename:
            if current is not None:
                found.append(current)
            current = [t]
        elif current is not None:
            if t in operators:
                found.append(current)
                current = None
            else:
                current.append(t)
    if current is not None:
        found.append(current)
    return found


# ----------------------------------------------------------------- transcript reading
def parse_ts(value):
    if isinstance(value, (int, float)):
        try:
            secs = value / 1000.0 if value > 1e11 else float(value)
            return datetime.datetime.fromtimestamp(secs, datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def load_entries(path):
    """JSONL (Claude Code, Cursor) or one JSON document with a message list (Gemini)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    stripped = raw.lstrip()
    if stripped.startswith("{") and "\n{" not in stripped.strip():
        try:
            doc = json.loads(stripped)
            if isinstance(doc, dict):
                for key in ("messages", "history", "conversation"):
                    if isinstance(doc.get(key), list):
                        return doc[key]
                return [doc]
        except ValueError:
            pass
    if stripped.startswith("["):
        doc = json.loads(stripped)
        return doc if isinstance(doc, list) else []
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def role_of(entry):
    role = entry.get("type") or entry.get("role") or (entry.get("message") or {}).get("role")
    role = str(role or "").lower()
    if role in ("gemini", "model", "assistant", "agent"):
        return "assistant"
    return role


def blocks_of(entry):
    msg = entry.get("message")
    content = msg.get("content") if isinstance(msg, dict) else entry.get("content")
    if isinstance(content, str):
        blocks = [{"type": "text", "text": content}]
    elif isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
    else:
        blocks = []
    for call in entry.get("toolCalls") or []:                 # Gemini CLI chat recording
        if isinstance(call, dict):
            blocks.append({"type": "tool_use", "name": call.get("name", ""),
                           "input": call.get("args") or {}})
    out = []
    for b in blocks:
        if b.get("type") in ("text", "output_text", "input_text") or (
                "text" in b and "type" not in b):
            out.append({"type": "text", "text": str(b.get("text", ""))})
        elif b.get("type") in ("tool_use", "tool_call", "function_call", "toolCall"):
            inp = b.get("input") or b.get("args") or b.get("arguments") or {}
            if isinstance(inp, str):
                try:
                    inp = json.loads(inp)
                except ValueError:
                    inp = {"command": inp}
            out.append({"type": "tool_use", "name": str(b.get("name", "")),
                        "input": inp if isinstance(inp, dict) else {}})
        elif b.get("type") in ("tool_result", "function_result"):
            out.append({"type": "tool_result"})
    return out


def is_real_user(entry):
    if role_of(entry) != "user" or entry.get("isSidechain"):
        return False
    return not any(b["type"] == "tool_result" for b in blocks_of(entry))


def user_text(entry):
    return "\n".join(b["text"] for b in blocks_of(entry) if b["type"] == "text")


def measure(entries):
    """Scope the last turn and measure it. Returns a dict, or None when nothing to judge."""
    start = None
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and is_real_user(entry):
            start = i
    if start is None:
        return None
    turn = [e for e in entries[start:] if isinstance(e, dict) and not e.get("isSidechain")]
    m = {"start_entry": entries[start], "user_text": user_text(entries[start]),
         "tool_calls": 0, "subagent": False, "sent_command": False, "asked": False,
         "spoke": False, "reply_chars": 0}
    for entry in turn[1:]:
        if role_of(entry) != "assistant":
            continue
        for block in blocks_of(entry):
            if block["type"] == "text":
                m["reply_chars"] += len(block["text"])
                continue
            if block["type"] != "tool_use":
                continue
            m["tool_calls"] += 1
            name = block["name"]
            if name in SUBAGENT_TOOLS:
                m["subagent"] = True
            if name in QUESTION_TOOLS:
                m["asked"] = True
            cmd = block["input"].get("command") or block["input"].get("cmd") or ""
            if isinstance(cmd, list):
                cmd = " ".join(str(c) for c in cmd)
            if not isinstance(cmd, str) or not (name in SHELL_TOOLS or cmd):
                continue
            if "notify.sh" in cmd:
                for tokens in invocations(cmd, "notify.sh"):
                    if "--dry-run" in tokens:
                        continue
                    if any(t in ("--code", "--code-only") or t.startswith(("--code=", "--code-only="))
                           for t in tokens):
                        m["sent_command"] = True
            if VOICE_BASENAME in cmd:
                for tokens in invocations(cmd, VOICE_BASENAME):
                    if not any(t in NOT_A_SEND for t in tokens):
                        m["spoke"] = True
    stamps = [t for t in (parse_ts(e.get("timestamp") or e.get("time")) for e in turn) if t]
    m["start"] = parse_ts(entries[start].get("timestamp") or entries[start].get("time")) or (
        stamps[0] if stamps else None)
    m["duration"] = (stamps[-1] - stamps[0]).total_seconds() if len(stamps) >= 2 else 0
    return m


def delivered_since(start):
    """True when the voice log has a 'sent note' line at or after `start`.

    None (fail open) when it cannot be decided: no start, no log, unreadable log."""
    if start is None:
        return None
    try:
        local_start = start.astimezone().replace(tzinfo=None) - datetime.timedelta(seconds=5)
        with open(nl.voice_log(), encoding="utf-8", errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 512 * 1024))
            lines = fh.read().splitlines()
    except Exception:                                         # noqa: BLE001
        return None
    for line in reversed(lines):
        try:
            stamp = datetime.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if stamp < local_start:
            return False
        if line[20:].startswith("sent note"):
            return True
    return False


def optout_phrases(cfg):
    raw = cfg.get("VOICE_HOOK_OPTOUT") or "no audio"
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def state_dir():
    return os.environ.get("VOICE_HOOK_STATE") or os.path.join(nl.STATE_DIR, "voice-hook")


def strikes(session, turn_key):
    """(count so far, path). The count resets when the turn changes."""
    path = os.path.join(state_dir(), re.sub(r"[^A-Za-z0-9._-]", "_", session or "unknown"))
    try:
        with open(path, encoding="utf-8") as fh:
            seen_key, seen_count = fh.read().split(None, 1)
        if seen_key == turn_key:
            return int(seen_count), path
    except Exception:                                         # noqa: BLE001
        pass
    return 0, path


def save_strike(path, turn_key, count):
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("%s %d" % (turn_key, count))
    except OSError:
        pass


def block_message(reasons):
    return (
        "Stop blocked by the voice-summary hook: this turn looks long, complex or "
        "decision-shaped, and no voice summary was delivered.\n\nWhy it qualifies:\n"
        + "\n".join("  - " + r for r in reasons) +
        "\n\nSend one before finishing (skill voice-summary):\n\n"
        "  " + VOICE_CMD + " --source AGENT --title \"<short title>\" \"<spoken summary>\"\n\n"
        "Write it for the ear: the conclusion first, narrate instead of listing, one to four "
        "minutes, and end with what you need from the user. Never read commands, paths, "
        "hashes or ids aloud; they stay in the written reply, and a command also goes there "
        "as a fenced block. Pick the --source that matches the work (TERRAFORM, DEPLOY, GCP, "
        "DB, SECURITY, BILLING, DNS, JIRA, ACTION). If the script prints a 'Markdown:' hub "
        "link, paste it into your reply. If it says the voice hub is not running, give the "
        "user the start command it printed instead of retrying. The user can skip this for "
        "one turn by writing \"no audio\" in the message.")


def main():
    client = client_from_argv(sys.argv[1:])
    try:
        cfg = nl.load_config(warn=False)
    except Exception:                                         # noqa: BLE001
        bail()
    if not nl.configured(cfg):
        bail()
    try:
        hook = json.load(sys.stdin)
    except Exception:                                         # noqa: BLE001
        bail()
    if not isinstance(hook, dict):
        bail()
    if client == "cursor" and as_int(hook.get("loop_count"), 0) >= MAX_BLOCKS_PER_TURN:
        bail()
    if client == "cursor" and hook.get("status") not in (None, "completed"):
        bail()                       # aborted or errored turns are not asked for a summary

    m = None
    path = hook.get("transcript_path")
    if path:
        try:
            m = measure(load_entries(path))
        except Exception:                                     # noqa: BLE001
            m = None
    if m is None:
        # No readable transcript: judge what the event itself carries (Gemini sends the
        # prompt and the response), and only the "wall of text" signal can be measured.
        prompt = hook.get("prompt") or ""
        response = hook.get("prompt_response") or hook.get("response") or ""
        if not isinstance(response, str) or not response:
            bail()
        m = {"start_entry": {}, "user_text": str(prompt), "tool_calls": 0, "subagent": False,
             "sent_command": False, "asked": False, "spoke": None,
             "reply_chars": len(response), "start": None, "duration": 0}

    text = (m["user_text"] or "").lower()
    if any(phrase in text for phrase in optout_phrases(cfg)):
        bail()

    long_s = as_int(cfg.get("VOICE_HOOK_LONG_SECONDS"), 240)
    calls = as_int(cfg.get("VOICE_HOOK_TOOL_CALLS"), 15)
    wall = as_int(cfg.get("VOICE_HOOK_REPLY_CHARS"), 1200)
    reasons = []
    if long_s > 0 and m["duration"] >= long_s:
        reasons.append("the turn ran %.0f minutes (long task)" % (m["duration"] / 60.0))
    if calls > 0 and m["tool_calls"] >= calls:
        reasons.append("%d tool calls (complex task)" % m["tool_calls"])
    if m["subagent"]:
        reasons.append("work was delegated to a subagent (complex task)")
    if m["sent_command"]:
        reasons.append("a command was sent to the user to run (decision)")
    if m["asked"]:
        reasons.append("a question was put to the user (decision)")
    if wall > 0 and m["reply_chars"] >= wall:
        reasons.append("the written reply is %d characters (a wall of text)" % m["reply_chars"])
    if not reasons:
        bail()

    if m["spoke"] is None:
        # The calls are invisible here: accept any delivery in the last half hour.
        recent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        if delivered_since(recent) is not False:
            bail()
    elif m["spoke"]:
        if delivered_since(m["start"]) is not False:
            bail()
        reasons.append("voice-note.py ran, but the voice log shows no delivery this turn "
                       "(it failed; read its error output)")

    entry = m["start_entry"]
    turn_key = str(entry.get("uuid") or entry.get("id") or hashlib.sha1(
        (m["user_text"] or "").encode("utf-8")).hexdigest()[:16])
    session = str(hook.get("session_id") or hook.get("conversation_id") or "unknown")
    count, spath = strikes(session, turn_key)
    if count >= MAX_BLOCKS_PER_TURN:
        sys.stderr.write("voice-summary hook: giving up after %d blocks on this turn.\n" % count)
        bail()
    save_strike(spath, turn_key, count + 1)

    message = block_message(reasons)
    if client == "cursor":
        sys.stdout.write(json.dumps({"followup_message": message}) + "\n")
        bail(0)
    sys.stderr.write(message + "\n")
    bail(2)


if __name__ == "__main__":
    main()
