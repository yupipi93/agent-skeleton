#!/usr/bin/env python3
"""Show how the AI Auto-Accept extension answers Claude Code permission prompts here.

AI Auto-Accept (VS Code / Cursor extension devcloudops.ai-auto-accept) installs a
PermissionRequest hook in <claude config dir>/settings.json that answers Yes to every
prompt Claude Code is about to show, except those matching its deny-list. This script
reads, never writes:

  - which Claude config dirs carry the hook, and which editor installed it;
  - the hook's live state (on / off, deny-list size) and the editor's user settings;
  - the decision log, and how many allowed prompts the recommended deny-list
    (kit/bundles/core/skills/permission-auto-accept/assets/deny-list.json) would have
    left to you.

  kit/bundles/core/scripts/auto-accept-audit.py
  kit/bundles/core/scripts/auto-accept-audit.py --show 20
  kit/bundles/core/scripts/auto-accept-audit.py --print-settings   # deny-list to paste

Environment:
  AUTO_ACCEPT_CLAUDE_DIRS  config dirs to read, os.pathsep-separated
                           (default: $CLAUDE_CONFIG_DIR, ~/.claude, ~/.claude.*)
  AUTO_ACCEPT_DENY_FILE    recommended deny-list JSON (default: the kit asset)
  AUTO_ACCEPT_EXTRA_DENY   extra deny-list JSON files, os.pathsep-separated, appended
                           to the recommended one (machine-specific patterns)

Exit codes: 0 fine or not installed, 1 warnings, 64 usage.
Read-only, Python 3.8+, stdlib only.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

KEY = "claudeAutoAccept.denyList"
HOOK_MARK = "ai-auto-accept"
ASSET = Path(__file__).resolve().parents[1] / "skills/permission-auto-accept/assets/deny-list.json"
EDITORS = ["Code", "Cursor", "Code - Insiders", "VSCodium", "Windsurf"]


def strip_jsonc(text):
    """Drop // and /* */ comments outside strings and trailing commas."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_json(path, jsonc=False):
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(strip_jsonc(text) if jsonc else text)
    except (OSError, ValueError):
        return None


def claude_dirs():
    env = os.environ.get("AUTO_ACCEPT_CLAUDE_DIRS")
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p]
    dirs = []
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        dirs.append(Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser())
    home = Path.home()
    dirs.append(home / ".claude")
    dirs += sorted(p for p in home.glob(".claude.*") if (p / "settings.json").is_file())
    seen, unique = set(), []
    for d in dirs:
        if d.resolve() not in seen:
            seen.add(d.resolve())
            unique.append(d)
    return unique


def hook_scripts(settings):
    """Paths of the auto-accept hook scripts referenced by PermissionRequest hooks."""
    found = []
    for group in ((settings or {}).get("hooks") or {}).get("PermissionRequest") or []:
        for hook in group.get("hooks") or []:
            cmd = hook.get("command") or ""
            if HOOK_MARK in cmd:
                m = re.search(r'"([^"]*%s[^"]*\.js)"' % HOOK_MARK, cmd) or re.search(r"(\S*%s\S*\.js)" % HOOK_MARK, cmd)
                found.append(Path(m.group(1)) if m else None)
    return found


def editor_of(path):
    for part in path.parts:
        if part in EDITORS:
            return part
    return "unknown editor"


def editor_settings():
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", ""))
    else:
        base = Path.home() / ".config"
    result = {}
    for name in EDITORS:
        data = load_json(base / name / "User/settings.json", jsonc=True)
        if data:
            keys = {k: v for k, v in data.items() if k.startswith("claudeAutoAccept.")}
            if keys:
                result[name] = keys
    return result


def recommended():
    files = [Path(os.environ.get("AUTO_ACCEPT_DENY_FILE") or ASSET)]
    files += [Path(p).expanduser() for p in os.environ.get("AUTO_ACCEPT_EXTRA_DENY", "").split(os.pathsep) if p]
    patterns = []
    for f in files:
        data = load_json(f)
        if data is None:
            sys.exit(f"cannot read deny-list file {f}")
        for p in data.get(KEY, data) if isinstance(data, dict) else data:
            if p not in patterns:
                patterns.append(p)
    return patterns


def compile_all(patterns):
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.IGNORECASE))
        except re.error:
            pass  # a JS-only construct; the extension still applies it
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--show", type=int, default=10, help="examples of risky allowed prompts to print (default 10)")
    ap.add_argument("--print-settings", action="store_true", help="print the recommended deny-list as a user-settings snippet")
    args = ap.parse_args()

    if args.print_settings:
        print(json.dumps({KEY: recommended()}, indent=2))
        return 0

    warn = 0
    storages = {}
    print("Claude config dirs")
    for d in claude_dirs():
        settings = load_json(d / "settings.json")
        if settings is None:
            continue
        hooks = hook_scripts(settings)
        if not hooks:
            print(f"  {d}: no auto-accept hook")
        for h in hooks:
            if h is None or not h.is_file():
                print(f"  {d}: hook points at a missing script ({h}); the prompt is shown as usual")
                warn += 1
                continue
            print(f"  {d}: hook installed by {editor_of(h)}")
            storages[h.parent] = editor_of(h)
    if not storages:
        print("\nAI Auto-Accept is not answering Claude Code prompts on this machine.")
        return 0

    rec = compile_all(recommended())
    for store, editor in storages.items():
        state = load_json(store / "state.json") or {}
        deny = state.get("deny") or []
        print(f"\nHook state ({editor}): claude {'on' if state.get('claude') else 'off'}, "
              f"copilot {'on' if state.get('copilot') else 'off'}, deny-list {len(deny)} patterns")
        if state.get("claude") and not deny:
            print("  WARN empty deny-list: every prompt is answered Yes, destructive ones included")
            warn += 1

        log = store / "decisions.jsonl"
        rows = []
        if log.is_file():
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
        allowed = [r for r in rows if r.get("decision") == "allow"]
        risky = [r for r in allowed if any(p.search(r.get("what", "")) for p in rec)]
        print(f"  decisions logged: {len(rows)} ({len(allowed)} answered Yes, {len(rows) - len(allowed)} left to you)")
        if risky:
            warn += 1
            print(f"  WARN {len(risky)} answered Yes that the recommended deny-list leaves to you"
                  " (approximate: the log keeps 160 characters)")
            for r in risky[-args.show:]:
                print(f"    {r.get('what', '')[:110]}")

    eds = editor_settings()
    print("\nEditor user settings")
    if not eds:
        print("  no claudeAutoAccept.* keys: the extension defaults apply")
    for name, keys in eds.items():
        print(f"  {name}: " + ", ".join(f"{k.split('.', 1)[1]}={json.dumps(v) if k != KEY else str(len(v)) + ' patterns'}"
                                       for k, v in sorted(keys.items())))
        if KEY in keys and not keys[KEY]:
            print(f"    WARN {KEY} is [] and replaces the built-in list: run --print-settings and paste it")
            warn += 1
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
