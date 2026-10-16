"""Command line: `avh <command>`. Every command an agent needs prints JSON with --json."""

import argparse
import json
import os
import subprocess
import sys

from . import __version__
from . import agents as agents_mod
from . import config as config_mod
from .store import Store


def _store(cfg):
    return Store(cfg["AVH_HOME"])


def _print(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return True
    return False


def _fmt_dur(seconds):
    seconds = int(round(seconds or 0))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def _git(cwd, *args):
    try:
        out = subprocess.check_output(["git", "-C", cwd] + list(args),
                                      stderr=subprocess.DEVNULL, timeout=10)
        return out.decode().strip()
    except Exception:                                       # noqa: BLE001
        return ""


# ------------------------------------------------------------------------- commands
def cmd_serve(args, cfg):
    from .server import serve
    serve(cfg, port=args.port, host=args.host)
    return 0


def cmd_add(args, cfg):
    """Ingest a note. Metadata from --meta-json (file or -) and/or flags; flags win."""
    meta = {}
    if args.meta_json:
        raw = sys.stdin.read() if args.meta_json == "-" else open(
            args.meta_json, encoding="utf-8").read()
        meta.update(json.loads(raw or "{}"))
    for key in ("title", "summary", "source", "tag", "speaker", "lang", "voice", "origin",
                "origin_ref", "created_at", "brief"):
        value = getattr(args, key, None)
        if value:
            meta[key] = value
    if args.speech_rate:
        meta["speech_rate"] = args.speech_rate
    if args.text_file:
        meta["text"] = open(args.text_file, encoding="utf-8").read()
    if args.link:
        meta["links"] = list(meta.get("links") or []) + args.link
    if args.commands_cli:
        meta["commands"] = list(meta.get("commands") or []) + [
            {"code": c, "label": "", "explanation": ""} for c in args.commands_cli]
    meta.setdefault("speech_rate", float(cfg.get("AVH_DEFAULT_SPEECH_RATE") or 1.0))
    # Who and where, unless the caller already said.
    if not meta.get("agent"):
        who = agents_mod.detect()
        meta.update({"agent": who["agent"], "agent_surface": who["surface"],
                     "agent_label": who["label"]})
        meta.setdefault("session_id", who["session_id"])
    cwd = meta.get("cwd") or os.getcwd()
    meta["cwd"] = cwd
    if not meta.get("repo"):
        top = _git(cwd, "rev-parse", "--show-toplevel")
        meta["repo"] = os.path.basename(top) if top else os.path.basename(cwd)
    if not meta.get("branch"):
        meta["branch"] = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    note = _store(cfg).add(args.audio, meta)
    out = {"id": note["id"], "urls": config_mod.note_urls(cfg, note["id"]),
           "duration": note["duration"], "summary": note["summary"],
           "agent": note["agent"], "agent_label": note["agent_label"]}
    if not _print(out, args.json):
        print(out["urls"].get("public") or out["urls"]["local"])
    return 0


def cmd_update(args, cfg):
    store = _store(cfg)
    if not store.get(args.id):
        sys.stderr.write("avh: no note %s\n" % args.id)
        return 1
    if args.channels_json:
        store.merge_channels(args.id, json.loads(args.channels_json))
    fields = {}
    for key in ("title", "summary"):
        if getattr(args, key):
            fields[key] = getattr(args, key)
    if args.heard is not None:
        from .store import now_iso
        fields["heard_at"] = now_iso() if args.heard == "yes" else None
    if fields:
        store.update(args.id, fields)
    _print(store.get(args.id), args.json)
    return 0


def cmd_list(args, cfg):
    notes = _store(cfg).list(q=args.q or "", agent=args.agent or "", tag=args.tag or "",
                             status="unheard" if args.unheard else "", limit=args.limit)
    if _print([{k: n[k] for k in ("id", "created_at", "title", "summary", "agent_label",
                                  "tag", "source", "duration", "heard_at")} |
               {"url": config_mod.note_urls(cfg, n["id"]).get("local")} for n in notes],
              args.json):
        return 0
    for n in notes:
        mark = " " if n["heard_at"] else "*"
        print("%s %s  %s  %-22s %-12s %s  %s" % (
            mark, n["id"], n["created_at"][:16].replace("T", " "),
            (n["agent_label"] or n["agent"])[:22], n["tag"][:12], _fmt_dur(n["duration"]),
            n["title"] or n["summary"][:60]))
    return 0


def cmd_show(args, cfg):
    note = _store(cfg).get(args.id)
    if not note:
        sys.stderr.write("avh: no note %s\n" % args.id)
        return 1
    note.pop("peaks", None)
    note["urls"] = config_mod.note_urls(cfg, note["id"])
    if _print(note, args.json):
        return 0
    print("%s  %s" % (note["title"], note["urls"]["local"]))
    print("%s · %s · %s · %s" % (note["agent_label"], note["tag"], note["source"],
                                 _fmt_dur(note["duration"])))
    print()
    print(note["text"] or note["spoken"])
    return 0


def cmd_url(args, cfg):
    note_id = args.id
    if note_id == "last":
        latest = _store(cfg).list(limit=1)
        if not latest:
            return 1
        note_id = latest[0]["id"]
    urls = config_mod.note_urls(cfg, note_id)
    print(urls.get("public") if args.public and urls.get("public") else urls["local"])
    return 0


def cmd_open(args, cfg):
    base = config_mod.local_url(cfg)
    url = base + ("/n/%s" % args.id if args.id else "/")
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.call([opener, url])
    except OSError:
        pass
    print(url)
    return 0


def cmd_resynth(args, cfg):
    """Re-record notes at the natural rate. Costs TTS characters: --dry-run first."""
    from . import resynth
    store = _store(cfg)
    if args.all:
        notes = [n for n in store.list(limit=100000, light=False, include_archived=True)
                 if n["speech_rate"] > 1.01 and (n["spoken"] or n["text"])]
        notes = notes[:args.limit] if args.limit else notes
    else:
        notes = [store.get(i) for i in args.ids]
        notes = [n for n in notes if n]
    total = resynth.chars_needed(notes)
    print("%d note(s), %d TTS characters" % (len(notes), total))
    if args.dry_run:
        return 0
    for i, n in enumerate(notes, 1):
        try:
            resynth.resynth(store, cfg, n)
            print("%d/%d %s ok" % (i, len(notes), n["id"]))
        except RuntimeError as exc:
            print("%d/%d %s FAILED: %s" % (i, len(notes), n["id"], exc))
    return 0


def cmd_command(args, cfg):
    """Attach a command or short explanation to this agent session's voice note."""
    session = args.session
    if session is None:
        session = agents_mod.detect().get("session_id") or ""
    note_id = _store(cfg).attach_command({"code": args.code, "label": args.label,
                                          "explanation": args.explanation}, session)
    print(note_id or "pending")
    return 0


def cmd_detect_agent(args, cfg):
    print(json.dumps(agents_mod.detect(), indent=2))
    return 0


def cmd_service(args, cfg):
    from . import service
    return service.run(args.action, cfg, tailnet=args.tailnet)


def cmd_doctor(args, cfg):
    from . import service
    return service.doctor(cfg)


def cmd_mcp(args, cfg):
    from . import mcp
    return mcp.run(cfg)


# ----------------------------------------------------------------------------- main
def main(argv=None):
    p = argparse.ArgumentParser(prog="avh", description="Agent Voice Hub %s" % __version__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("serve", help="run the web server (the login service does this)")
    sp.add_argument("--port", type=int)
    sp.add_argument("--host")
    sp.set_defaults(fn=cmd_serve)

    sp = sub.add_parser("add", help="store a note: audio file plus metadata")
    sp.add_argument("--audio", required=True, help="any audio ffmpeg reads")
    sp.add_argument("--meta-json", help="JSON metadata file, or - for stdin")
    sp.add_argument("--title")
    sp.add_argument("--summary")
    sp.add_argument("--source")
    sp.add_argument("--tag")
    sp.add_argument("--speaker")
    sp.add_argument("--lang")
    sp.add_argument("--voice")
    sp.add_argument("--speech-rate", type=float, dest="speech_rate")
    sp.add_argument("--text-file", dest="text_file")
    sp.add_argument("--link", action="append", help="URL to show with the note (repeatable)")
    sp.add_argument("--command", action="append", dest="commands_cli",
                    help="command to show first, with a copy button (repeatable)")
    sp.add_argument("--brief", help="short written explanation shown first")
    sp.add_argument("--origin")
    sp.add_argument("--origin-ref", dest="origin_ref")
    sp.add_argument("--created-at", dest="created_at")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_add)

    sp = sub.add_parser("update", help="change a note (delivery status, title, heard)")
    sp.add_argument("id")
    sp.add_argument("--channels-json", dest="channels_json")
    sp.add_argument("--title")
    sp.add_argument("--summary")
    sp.add_argument("--heard", choices=("yes", "no"))
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_update)

    sp = sub.add_parser("list", help="recent notes (* = not heard yet)")
    sp.add_argument("-n", "--limit", type=int, default=20)
    sp.add_argument("-q", help="search text")
    sp.add_argument("--agent")
    sp.add_argument("--tag")
    sp.add_argument("--unheard", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("show", help="one note with its full text")
    sp.add_argument("id")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser("url", help="player URL of a note ('last' for the newest)")
    sp.add_argument("id")
    sp.add_argument("--public", action="store_true", help="the tailnet URL (phone)")
    sp.set_defaults(fn=cmd_url)

    sp = sub.add_parser("open", help="open the hub (or one note) in the browser")
    sp.add_argument("id", nargs="?")
    sp.set_defaults(fn=cmd_open)

    sp = sub.add_parser("resynth", help="re-record notes at the natural rate (costs TTS)")
    sp.add_argument("ids", nargs="*")
    sp.add_argument("--all", action="store_true", help="every note recorded faster than 1x")
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--dry-run", action="store_true", help="only count the characters")
    sp.set_defaults(fn=cmd_resynth)

    sp = sub.add_parser("command", help="attach a command/explanation to the session's note")
    sp.add_argument("action", choices=("add",))
    sp.add_argument("--code", default="")
    sp.add_argument("--label", default="", help="short title for the command")
    sp.add_argument("--explanation", default="", help="one or two sentences of context")
    sp.add_argument("--session", help="agent session id (default: detected)")
    sp.set_defaults(fn=cmd_command)

    sp = sub.add_parser("detect-agent", help="print which agent this shell belongs to")
    sp.set_defaults(fn=cmd_detect_agent)

    sp = sub.add_parser("service", help="login service (launchd), optional Tailscale Serve")
    sp.add_argument("action", choices=("install", "uninstall", "restart", "status"))
    sp.add_argument("--tailnet", action="store_true",
                    help="install: also publish the hub on your tailnet (Tailscale Serve)")
    sp.set_defaults(fn=cmd_service)

    sp = sub.add_parser("doctor", help="check everything the hub depends on")
    sp.set_defaults(fn=cmd_doctor)

    sp = sub.add_parser("mcp", help="run the MCP server on stdio")
    sp.set_defaults(fn=cmd_mcp)

    args = p.parse_args(argv)
    # Notes are work content: everything this process creates is private to the user.
    os.umask(0o077)
    cfg = config_mod.load()
    return args.fn(args, cfg)
