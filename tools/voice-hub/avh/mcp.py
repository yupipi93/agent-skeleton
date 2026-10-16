"""MCP server on stdio: the voice notes as tools, plus an inline player (MCP Apps).

Every MCP client gets the plain tools (list recent notes, read one, get its link), which
is how an agent answers "what did the payments agent tell me yesterday?" without
opening a browser.

Clients that implement the MCP Apps extension (io.modelcontextprotocol/ui; Cursor
since 2.6, VS Code Copilot since 1.109) also render `voice_note_play` as a player
inside the chat. The player never loads audio from the network: it pulls the MP3
through the app-only tool `voice_note_audio_chunk` and plays it from a data: URL, which
the default MCP Apps CSP already allows. That keeps it working whatever the host
thinks of http://127.0.0.1, and it keeps the audio bytes out of the model's context
(the chunk tool is app-only, so the agent never sees it).

Protocol: JSON-RPC 2.0, one message per line. Standard library only.
"""

import base64
import json
import os
import sys

from . import __version__
from . import agents as agents_mod
from . import config as config_mod
from .store import Store

UI_URI = "ui://agent-voice-hub/player.html"
UI_MIME = "text/html;profile=mcp-app"
UI_EXT = "io.modelcontextprotocol/ui"
CHUNK = 384 * 1024
PLAYER_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "mcp-player.html")

TOOLS = [
    {
        "name": "voice_notes_recent",
        "title": "Recent voice notes",
        "description": "List the most recent spoken summaries the agents sent to the user "
                       "(title, agent, project, length, heard or not, player link). Use it "
                       "to find what an agent reported, or to check that a note arrived.",
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            "unheard_only": {"type": "boolean", "default": False},
            "query": {"type": "string", "description": "text, ticket key or project"},
            "agent": {"type": "string", "enum": list(agents_mod.AGENTS)},
        }},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "voice_note_get",
        "title": "Read a voice note",
        "description": "Full text, transcript and metadata of one voice note, by id "
                       "('last' for the newest).",
        "inputSchema": {"type": "object", "required": ["id"],
                        "properties": {"id": {"type": "string"}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "voice_note_play",
        "title": "Play a voice note",
        "description": "Show a voice note with an audio player (inline where the client "
                       "supports MCP Apps, otherwise a link to the Voice Hub player). Use it "
                       "right after sending a note, or when the user asks to listen to one. "
                       "id defaults to the newest note.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
        "annotations": {"readOnlyHint": True},
        "_meta": {"ui": {"resourceUri": UI_URI, "visibility": ["model", "app"]}},
    },
    {
        "name": "voice_note_audio_chunk",
        "title": "Audio bytes (player only)",
        "description": "Base64 slice of a note's MP3. Used by the inline player only.",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}}},
        "annotations": {"readOnlyHint": True},
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": "voice_note_mark_heard",
        "title": "Mark a voice note as heard",
        "description": "Mark a note as heard (or not heard with heard=false).",
        "inputSchema": {"type": "object", "required": ["id"], "properties": {
            "id": {"type": "string"}, "heard": {"type": "boolean", "default": True}}},
        "_meta": {"ui": {"visibility": ["model", "app"]}},
    },
]


class Server:
    def __init__(self, cfg):
        self.cfg = cfg
        self.store = Store(cfg["AVH_HOME"])
        self.ui = False

    # ---------------------------------------------------------------- helpers
    def _note(self, note_id):
        if not note_id or note_id == "last":
            rows = self.store.list(limit=1)
            return self.store.get(rows[0]["id"]) if rows else None
        return self.store.get(note_id)

    def _urls(self, note_id):
        return config_mod.note_urls(self.cfg, note_id)

    def _line(self, n):
        urls = self._urls(n["id"])
        mins = int(n["duration"] // 60), int(n["duration"] % 60)
        return "- [%s] %s · %s · %s · %d:%02d%s\n  %s\n  id %s · %s" % (
            n["created_at"][:16].replace("T", " ") + "Z", n["title"] or n["summary"][:60],
            n["agent_label"] or n["agent"], n["tag"] or "-", mins[0], mins[1],
            "" if n["heard_at"] else " · UNHEARD", n["summary"] or "", n["id"],
            urls["local"])

    def _public(self, n, full=False):
        out = {k: n[k] for k in ("id", "created_at", "title", "summary", "source", "tag",
                                 "agent", "agent_label", "duration", "speech_rate",
                                 "heard_at", "starred", "tickets", "peaks", "segments",
                                 "audio_bytes")}
        name, badge, color = agents_mod.badge(n["agent"])
        out.update({"agent_badge": badge, "agent_color": color, "urls": self._urls(n["id"])})
        if full:
            out.update({"commands": n.get("commands") or [], "brief": n.get("brief") or "",
                        "text": n["text"], "spoken": n["spoken"], "session_id": n["session_id"],
                        "cwd": n["cwd"], "links": n["links"], "channels": n["channels"]})
        return out

    # ------------------------------------------------------------------ tools
    def call(self, name, args):
        if name == "voice_notes_recent":
            notes = self.store.list(q=args.get("query") or "", agent=args.get("agent") or "",
                                    status="unheard" if args.get("unheard_only") else "",
                                    limit=int(args.get("limit") or 10))
            if not notes:
                return _text("No notes match the filter.")
            body = "\n".join(self._line(n) for n in notes)
            return {"content": [{"type": "text", "text": body}],
                    "structuredContent": {"notes": [{k: n[k] for k in (
                        "id", "created_at", "title", "summary", "agent_label", "tag",
                        "duration", "heard_at")} for n in notes]}}
        if name == "voice_note_get":
            n = self._note(args.get("id"))
            if not n:
                return _error("No note %s" % args.get("id"))
            cmds = "".join("\n%s\n```\n%s\n```" % (c.get("label") or c.get("explanation") or "",
                                                     c.get("code") or "")
                           for c in n.get("commands") or [] if c.get("code"))
            text = "%s\n%s\n%s%s\n\n%s\n\nListen: %s" % (
                self._line(n), "Tickets: " + ", ".join(n["tickets"]) if n["tickets"] else "",
                n.get("brief") or "", cmds,
                n["text"] or n["spoken"] or "(no text: this note has audio only)",
                self._urls(n["id"]).get("public") or self._urls(n["id"])["local"])
            return {"content": [{"type": "text", "text": text}],
                    "structuredContent": self._public(n, full=True)}
        if name == "voice_note_play":
            n = self._note(args.get("id"))
            if not n:
                return _error("No notes yet." if not args.get("id")
                              else "No note %s" % args.get("id"))
            urls = self._urls(n["id"])
            text = "🎧 %s (%s, %d:%02d)\nListen on this machine: %s%s" % (
                n["title"] or n["summary"], n["agent_label"], n["duration"] // 60,
                n["duration"] % 60, urls["local"],
                ("\nOn the phone: " + urls["public"]) if urls.get("public") else "")
            return {"content": [{"type": "text", "text": text}],
                    "structuredContent": {"note": self._public(n)}}
        if name == "voice_note_audio_chunk":
            n = self._note(args.get("id"))
            path = self.store.audio_path(n) if n else ""
            if not path or not os.path.exists(path):
                return _error("audio not found")
            offset = int(args.get("offset") or 0)
            size = os.path.getsize(path)
            with open(path, "rb") as fh:
                fh.seek(offset)
                data = fh.read(CHUNK)
            nxt = offset + len(data)
            return {"content": [{"type": "text", "text": "chunk %d-%d of %d" % (
                offset, nxt, size)}],
                    "structuredContent": {"offset": offset, "next": nxt if nxt < size else None,
                                          "size": size, "mime": "audio/mpeg",
                                          "data": base64.b64encode(data).decode("ascii")}}
        if name == "voice_note_mark_heard":
            from .store import now_iso
            n = self._note(args.get("id"))
            if not n:
                return _error("No note %s" % args.get("id"))
            self.store.update(n["id"], {"heard_at": now_iso() if args.get("heard", True)
                                        else None})
            return _text("Done.")
        return _error("unknown tool %s" % name)

    # ---------------------------------------------------------------- jsonrpc
    def handle(self, msg):
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "initialize":
            caps = (params.get("capabilities") or {})
            exts = caps.get("extensions") or (caps.get("experimental") or {}).get(
                "extensions") or {}
            self.ui = UI_EXT in exts
            return {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False},
                                     "resources": {"listChanged": False},
                                     "extensions": {UI_EXT: {}}},
                    "serverInfo": {"name": "agent-voice-hub", "title": "Agent Voice Hub",
                                   "version": __version__},
                    "instructions": "Voice notes are the spoken summaries agents send the "
                                    "user with kit/bundles/voice/scripts/voice-note.py. Use "
                                    "voice_notes_recent to look them up and voice_note_play "
                                    "to show a player."}
        if method == "ping":
            return {}
        if method == "tools/list":
            # A client without MCP Apps would show app-only tools to the model, which
            # would then be tempted to pull megabytes of base64 audio into its context.
            if self.ui:
                return {"tools": TOOLS}
            return {"tools": [t for t in TOOLS
                              if "model" in ((t.get("_meta") or {}).get("ui") or {}).get(
                                  "visibility", ["model"])]}
        if method == "tools/call":
            try:
                return self.call(params.get("name"), params.get("arguments") or {})
            except Exception as exc:                          # noqa: BLE001
                return _error("error: %s" % exc)
        if method == "resources/list":
            return {"resources": [{"uri": UI_URI, "name": "Voice note player",
                                   "mimeType": UI_MIME}]}
        if method == "resources/read":
            if params.get("uri") != UI_URI:
                raise ValueError("unknown resource %s" % params.get("uri"))
            with open(PLAYER_HTML, encoding="utf-8") as fh:
                html = fh.read()
            return {"contents": [{"uri": UI_URI, "mimeType": UI_MIME, "text": html,
                                  "_meta": {"ui": {"prefersBorder": True,
                                                   "csp": {"resourceDomains": [],
                                                           "connectDomains": []}}}}]}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "prompts/list":
            return {"prompts": []}
        raise LookupError(method)


def _text(t):
    return {"content": [{"type": "text", "text": t}]}


def _error(t):
    return {"content": [{"type": "text", "text": t}], "isError": True}


def run(cfg=None):
    server = Server(cfg or config_mod.load())
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "id" not in msg:          # notification
            continue
        try:
            result = server.handle(msg)
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        except LookupError as exc:
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32601, "message": "method not found: %s" % exc}}
        except Exception as exc:                              # noqa: BLE001
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32603, "message": str(exc)}}
        out.write(json.dumps(reply, ensure_ascii=False) + "\n")
        out.flush()
    return 0
