"""Which agent produced a note, worked out from the environment it ran in.

People run several agents at once (Claude Code in a terminal, Claude Code inside
Cursor, Cursor's own agent, sessions driven from a phone through T3 Code), so a note
that does not say where it came from is a note the listener has to go and place. The caller
never has to pass this: the shell an agent runs a command in already carries enough
fingerprints. Order matters, most specific first.

Evidence, in decreasing order of trust:
  1. An explicit override: --agent on the CLI, or AVH_AGENT in the environment.
  2. Documented variables the agents set for their child shells (CLAUDECODE,
     CLAUDE_CODE_ENTRYPOINT, CURSOR_AGENT, GEMINI_CLI, CODEX_*...).
  3. The process ancestry, read with `ps`: an unknown launcher still shows up as
     `claude`, `cursor-agent` or `Cursor Helper` somewhere above the shell.
"""

import os
import subprocess

# id -> (label, short badge, colour). The UI uses the badge and colour; the label is
# what the detail view and the MCP tools print.
AGENTS = {
    "claude-code": ("Claude Code", "CC", "#d97757"),
    "cursor": ("Cursor Agent", "CU", "#7c8cff"),
    "gemini": ("Gemini CLI", "GE", "#4b8bf5"),
    "antigravity": ("Antigravity", "AG", "#a970ff"),
    "codex": ("Codex", "CX", "#10a37f"),
    "unknown": ("Agent", "AI", "#8a8f98"),
}

SURFACES = {
    "terminal": "terminal",
    "cursor": "in Cursor",
    "vscode": "in VS Code",
    "t3": "via T3 Code",
    "desktop": "Desktop",
    "remote": "remote",
    "sdk": "via SDK",
    "cli": "CLI",
    "ide": "IDE",
}


def _env(env, *names):
    for name in names:
        value = env.get(name)
        if value:
            return value
    return ""


def _in_cursor(env):
    """True when the process tree is hosted by the Cursor editor."""
    if any(k.startswith("CURSOR_") for k in env):
        return True
    for key in ("VSCODE_CWD", "VSCODE_GIT_ASKPASS_MAIN", "__CFBundleIdentifier",
                "VSCODE_CODE_CACHE_PATH"):
        value = env.get(key, "")
        if "Cursor" in value or "todesktop" in value:
            return True
    return False


def _in_t3(env):
    return any(k.startswith("T3CODE") for k in env)


def _ancestry(pid=None, depth=12):
    """Command names of the parent chain, nearest first. Never raises."""
    names = []
    pid = pid or os.getppid()
    for _ in range(depth):
        if not pid or pid <= 1:
            break
        try:
            out = subprocess.check_output(["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                                          stderr=subprocess.DEVNULL, timeout=5)
        except Exception:                                   # noqa: BLE001
            break
        line = out.decode("utf-8", "replace").strip()
        if not line:
            break
        ppid, _, comm = line.partition(" ")
        names.append(comm.strip().rsplit("/", 1)[-1])
        try:
            pid = int(ppid)
        except ValueError:
            break
    return names


def detect(env=None, ancestry=None):
    """Return a dict: agent, surface, label, session_id. Pure given its inputs."""
    env = dict(os.environ if env is None else env)
    override = _env(env, "AVH_AGENT")
    session = ""
    agent, surface = "unknown", ""

    if override:
        agent = override if override in AGENTS else "unknown"
        surface = _env(env, "AVH_AGENT_SURFACE")
        label = AGENTS[agent][0] if agent != "unknown" else override
        return {"agent": agent, "surface": surface, "label": _label(label, surface),
                "session_id": _env(env, "AVH_SESSION_ID")}

    # Claude first: Claude Code running inside Cursor also inherits CURSOR_* variables.
    if env.get("CLAUDECODE") == "1" or env.get("CLAUDE_CODE_ENTRYPOINT"):
        agent = "claude-code"
        entry = env.get("CLAUDE_CODE_ENTRYPOINT", "")
        session = _env(env, "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")
        if _in_t3(env):
            surface = "t3"
        elif entry == "claude-vscode":
            surface = "cursor" if _in_cursor(env) else "vscode"
        elif entry == "claude-desktop":
            surface = "desktop"
        elif entry.startswith("remote"):
            surface = "remote"
        elif entry.startswith("sdk"):
            surface = "sdk"
        else:
            surface = "terminal"
    elif _env(env, "GEMINI_CLI"):
        agent, surface = "gemini", "cli"
    elif _env(env, "ANTIGRAVITY_AGENT", "ANTIGRAVITY_CLI_ALIAS"):
        agent, surface = "antigravity", "ide"
    elif _env(env, "CODEX_THREAD_ID", "CODEX_SANDBOX", "CODEX_CI"):
        agent, surface = "codex", "cli"
        session = _env(env, "CODEX_THREAD_ID")
    elif env.get("CURSOR_AGENT") == "1":
        agent, surface = "cursor", "cli"
    elif env.get("CURSOR_TRACE_ID") or env.get("CURSOR_EXTENSION_HOST_ROLE") == "agent-exec":
        agent, surface = "cursor", "ide"
        session = _env(env, "CURSOR_CONVERSATION_ID")
    elif env.get("AI_AGENT"):
        # Vercel's proposed convention: "<name>_<version>_agent".
        name = env["AI_AGENT"].split("_")[0].lower()
        for key in AGENTS:
            if key != "unknown" and key.split("-")[0] in name:
                agent, surface = key, ""
                break

    if agent == "unknown":
        names = [n.lower() for n in (ancestry if ancestry is not None else _ancestry())]
        joined = " ".join(names)
        if "cursor-agent" in joined:
            agent, surface = "cursor", "cli"
        elif "claude" in joined:
            agent, surface = "claude-code", "terminal"
        elif "gemini" in joined:
            agent, surface = "gemini", "cli"
        elif "antigravity" in joined:
            agent, surface = "antigravity", "ide"
        elif "codex" in joined:
            agent, surface = "codex", "cli"
        elif "cursor" in joined:
            agent, surface = "cursor", "ide"

    return {"agent": agent, "surface": surface,
            "label": _label(AGENTS[agent][0], surface), "session_id": session}


def _label(name, surface):
    if name == AGENTS["cursor"][0]:
        return {"cli": "Cursor CLI"}.get(surface, name)
    where = SURFACES.get(surface, surface)
    if not where or name.lower().endswith(where.lower()):
        return name
    return "%s %s" % (name, where)


def badge(agent):
    return AGENTS.get(agent, AGENTS["unknown"])
