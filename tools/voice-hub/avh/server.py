"""The web server: the player UI, a small JSON API, the audio files and a live event feed.

Standard library only (ThreadingHTTPServer), bound to loopback. A phone can reach it
through Tailscale Serve (opt-in), which terminates HTTPS on the tailnet and proxies here.

Things that are easy to get wrong and are handled on purpose:
  * Range requests. Chrome seeks a media element with `Range: bytes=N-` and needs a 206
    back, or the scrubber does nothing. Single ranges, open ranges and suffix ranges
    are honoured; anything unsatisfiable gets a 416 with `bytes */size`.
  * DNS rebinding. Only Host headers we expect are answered, so a web page somewhere
    else cannot point a hostname at 127.0.0.1 and read the notes.
  * CSRF. Every write needs the `X-AVH: 1` header, which a cross-site form cannot send
    and a cross-site fetch cannot send without a CORS preflight we never approve.
  * Live updates. The CLI writes from another process, so the event feed polls SQLite's
    PRAGMA data_version (bumped by other connections' commits) and tells the browser.
"""

import json
import mimetypes
import os
import re
import select
import socket
import sqlite3
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from . import agents as agents_mod
from . import config as config_mod
from .store import Store, now_iso

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
NOTE_PATH = re.compile(r"^/n/([A-Za-z0-9]{4,40})/?$")
API_NOTE = re.compile(r"^/api/notes/([A-Za-z0-9]{4,40})$")
API_RESYNTH = re.compile(r"^/api/notes/([A-Za-z0-9]{4,40})/resynth$")
MEDIA = re.compile(r"^/media/([A-Za-z0-9]{4,40})\.mp3$")
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
PLAY_HANDOFF_TIMEOUT = 2.5     # seconds an open hub tab gets to start a note from a link

mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")


def parse_range(header, size):
    """(start, end) inclusive for a single byte range, None for "no range", or "bad".

    Multi-range requests are answered with the first range only, which every media
    client accepts; nobody seeks audio with multipart/byteranges.
    """
    if not header:
        return None
    header = header.strip().split(",")[0].strip()
    m = RANGE_RE.match(header)
    if not m or size <= 0:
        return "bad"
    first, last = m.group(1), m.group(2)
    if first == "" and last == "":
        return "bad"
    if first == "":                      # suffix: the last N bytes
        n = int(last)
        if n == 0:
            return "bad"
        return max(0, size - n), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if start >= size or end < start:
        return "bad"
    return start, min(end, size - 1)


class Hub:
    """Shared state for the request handlers."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.store = Store(cfg["AVH_HOME"])
        self.started = now_iso()
        self.allowed_hosts = self._hosts()
        self.allowed_logins = {x.strip().lower() for x in
                               (cfg.get("AVH_ALLOWED_LOGINS") or "").split(",") if x.strip()}
        # Tab-to-tab signals ("play this note", "I am playing it") fanned out to every
        # open event stream. A condition, not polling, so a click plays at once.
        self.cond = threading.Condition()
        self.signals = []
        self.seq = 0
        self.players = {}        # host -> open event streams of tabs that hold the player role
        self.acks = {}           # play request -> tab that is playing it

    def player_streams(self, host):
        with self.cond:
            return self.players.get(host, 0)

    def add_player(self, host, delta):
        with self.cond:
            self.players[host] = max(0, self.players.get(host, 0) + delta)

    def ack(self, req, tab):
        with self.cond:
            self.acks[req] = tab
            while len(self.acks) > 50:
                del self.acks[next(iter(self.acks))]
        return self.signal("play-ack", {"req": req, "tab": tab})

    def wait_ack(self, req, timeout):
        """The tab that took play request `req`, or None if nobody did within `timeout`."""
        deadline = time.monotonic() + timeout
        with self.cond:
            while req not in self.acks:
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.cond.wait(left)
            return self.acks[req]

    def signal(self, event, data):
        with self.cond:
            self.seq += 1
            self.signals.append((self.seq, event, data))
            del self.signals[:-50]
            self.cond.notify_all()
            return self.seq

    def signals_after(self, seq):
        with self.cond:
            return [x for x in self.signals if x[0] > seq]

    def _hosts(self):
        port = self.cfg["AVH_PORT"]
        hosts = {"127.0.0.1:%s" % port, "localhost:%s" % port, "[::1]:%s" % port}
        pub = config_mod.public_url(self.cfg)
        if pub:
            netloc = urllib.parse.urlparse(pub).netloc
            hosts.add(netloc)
            hosts.add(netloc.split(":")[0])
        return hosts


class Handler(BaseHTTPRequestHandler):
    server_version = "agent-voice-hub/" + __version__
    protocol_version = "HTTP/1.1"
    hub = None   # set by serve()

    # ----------------------------------------------------------------- plumbing
    def log_message(self, fmt, *args):
        if os.environ.get("AVH_ACCESS_LOG"):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    def _guard(self):
        host = (self.headers.get("Host") or "").lower()
        if host not in self.hub.allowed_hosts:
            self._send_json({"error": "unexpected host"}, HTTPStatus.MISDIRECTED_REQUEST)
            return False
        login = (self.headers.get("Tailscale-User-Login") or "").lower()
        if login and self.hub.allowed_logins and login not in self.hub.allowed_logins:
            self._send_json({"error": "tailnet user not allowed"}, HTTPStatus.FORBIDDEN)
            return False
        return True

    def _send(self, status, body=b"", ctype="text/plain; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _send_json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 2_000_000:
            raise ValueError("body too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _query(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, {k: v[-1] for k, v in urllib.parse.parse_qs(parsed.query).items()}

    # ------------------------------------------------------------------- verbs
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._guard():
            return
        path, qs = self._query()
        try:
            m = NOTE_PATH.match(path)
            if m and qs.get("play") == "1" and not qs.get("tried") and self.command == "GET":
                return self._play_link(m.group(1))
            if path in ("/", "/index.html") or m:
                return self._static("index.html", cache="no-cache")
            if path == "/healthz":
                return self._send_json({"ok": True, "version": __version__,
                                        "started": self.hub.started})
            if path == "/api/config":
                return self._api_config()
            if path == "/api/notes":
                return self._api_list(qs)
            if path == "/api/facets":
                return self._send_json(self.hub.store.facets())
            m = API_NOTE.match(path)
            if m:
                return self._api_get(m.group(1))
            m = MEDIA.match(path)
            if m:
                return self._media(m.group(1))
            if path == "/api/events":
                try:
                    return self._events(player=qs.get("player") == "1")
                except (OSError, sqlite3.Error):
                    return None          # client gone or data dir gone: end the stream
            if path in ("/sw.js", "/manifest.webmanifest"):
                return self._static(path.lstrip("/"), cache="no-cache")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):], cache="no-cache")
            return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (BrokenPipeError, ConnectionResetError):
            return None

    def do_PATCH(self):
        if not self._guard() or not self._csrf_ok():
            return
        path, _ = self._query()
        m = API_NOTE.match(path)
        if not m:
            return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            body = self._read_json()
        except ValueError as exc:
            return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        fields = {}
        if "heard" in body:
            fields["heard_at"] = now_iso() if body["heard"] else None
        if "starred" in body:
            fields["starred"] = 1 if body["starred"] else 0
        if "archived" in body:
            fields["archived"] = 1 if body["archived"] else 0
        if "position" in body:
            try:
                fields["position"] = max(0.0, float(body["position"]))
            except (TypeError, ValueError):
                pass
        for key in ("title", "summary"):
            if isinstance(body.get(key), str):
                fields[key] = body[key][:500]
        if not self.hub.store.get(m.group(1)):
            return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        note = self.hub.store.update(m.group(1), fields)
        return self._send_json(self._decorate(note))

    def do_POST(self):
        if not self._guard() or not self._csrf_ok():
            return
        path, _ = self._query()
        if path == "/api/play":
            # "Play this note": a freshly opened link asks the hub tab that is already
            # open (and already allowed to make sound) to play it instead.
            try:
                body = self._read_json()
            except ValueError as exc:
                return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            req = self.hub.signal("play", {"id": str(body.get("id", ""))[:40],
                                           "from": str(body.get("from", ""))[:40],
                                           "host": (self.headers.get("Host") or "").lower()})
            return self._send_json({"req": req})
        if path == "/api/play-ack":
            try:
                body = self._read_json()
            except ValueError as exc:
                return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            self.hub.ack(int(body.get("req") or 0), str(body.get("tab", ""))[:40])
            return self._send_json({"ok": True})
        m = API_RESYNTH.match(path)
        if m:
            from . import resynth
            note = self.hub.store.get(m.group(1))
            if not note:
                return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            try:
                note = resynth.resynth(self.hub.store, self.hub.cfg, note)
            except RuntimeError as exc:
                return self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return self._send_json(self._decorate(note))
        if path == "/api/notes/mark-all-heard":
            return self._send_json({"marked": self.hub.store.mark_all_heard()})
        return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _csrf_ok(self):
        if self.headers.get("X-AVH") != "1":
            self._send_json({"error": "missing X-AVH header"}, HTTPStatus.FORBIDDEN)
            return False
        return True

    # ---------------------------------------------------------------- handlers
    def _decorate(self, note):
        if not note:
            return note
        badge = agents_mod.badge(note.get("agent"))
        note["agent_name"], note["agent_badge"], note["agent_color"] = badge
        # The version makes caches (the phone's service worker included) fetch a
        # re-synthesised recording instead of serving the old one.
        note["audio_url"] = "/media/%s.mp3?v=%s" % (note["id"], note.get("audio_bytes") or 0)
        note["can_resynth"] = bool(note.get("speech_rate", 1) > 1.01 and
                                   (note.get("spoken") or note.get("text")))
        note["urls"] = config_mod.note_urls(self.hub.cfg, note["id"])
        return note

    def _api_config(self):
        cfg = self.hub.cfg
        return self._send_json({
            "version": __version__,
            "local_url": config_mod.local_url(cfg),
            "public_url": config_mod.public_url(cfg),
            "default_speech_rate": float(cfg.get("AVH_DEFAULT_SPEECH_RATE") or 1.5),
            "agents": {k: {"name": v[0], "badge": v[1], "color": v[2]}
                       for k, v in agents_mod.AGENTS.items()},
            "ticket_links": config_mod.ticket_links(cfg),
        })

    def _api_list(self, qs):
        try:
            limit = max(1, min(500, int(qs.get("limit") or 60)))
        except ValueError:
            limit = 60
        notes = self.hub.store.list(q=qs.get("q", ""), agent=qs.get("agent", ""),
                                    tag=qs.get("tag", ""), source=qs.get("source", ""),
                                    status=qs.get("status", ""), limit=limit,
                                    before=qs.get("before", ""))
        return self._send_json({"notes": [self._decorate(n) for n in notes],
                                "has_more": len(notes) == limit})

    def _api_get(self, note_id):
        note = self.hub.store.get(note_id)
        if not note:
            return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        return self._send_json(self._decorate(note))

    def _media(self, note_id):
        note = self.hub.store.get(note_id)
        path = self.hub.store.audio_path(note) if note else ""
        if not path or not os.path.exists(path):
            return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        size = os.path.getsize(path)
        rng = None if self.command == "HEAD" else parse_range(self.headers.get("Range"), size)
        common = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=31536000",
                  "Content-Disposition": "inline; filename=\"%s.mp3\"" % note_id}
        if rng == "bad":
            common["Content-Range"] = "bytes */%d" % size
            return self._send(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, b"",
                              "audio/mpeg", common)
        start, end = (0, size - 1) if rng is None else rng
        length = end - start + 1
        self.send_response(HTTPStatus.OK if rng is None else HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(length))
        if rng is not None:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        for k, v in common.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command == "HEAD":
            return None
        with open(path, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                buf = fh.read(min(65536, left))
                if not buf:
                    break
                try:
                    self.wfile.write(buf)
                except (BrokenPipeError, ConnectionResetError):
                    return None     # Chrome aborts range requests when it seeks
                left -= len(buf)
        return None

    def _play_link(self, note_id):
        """A `?play=1` link (the one agents put in chat replies) was opened.

        If a hub tab for this host is already open and holds the player role, it plays
        the note and this request answers with a tiny page that closes itself, so the
        click feels like "play" instead of "open the hub again". Done here, before the
        app loads, because waiting for the new tab's JavaScript to ask took seconds.
        Otherwise the full app loads and plays the note itself (`tried=1`).
        """
        host = (self.headers.get("Host") or "").lower()
        tab, t0 = None, time.monotonic()
        players = self.hub.player_streams(host)
        if players and self.hub.store.get(note_id):
            req = self.hub.signal("play", {"id": note_id, "from": "link", "host": host})
            tab = self.hub.wait_ack(req, PLAY_HANDOFF_TIMEOUT)
        sys.stderr.write("%s play-link %s players=%d handoff=%s in %dms ua=%s\n" % (
            self.log_date_time_string(), note_id, players, tab or "none",
            (time.monotonic() - t0) * 1000, (self.headers.get("User-Agent") or "")[-60:]))
        if tab:
            return self._static("handoff.html", cache="no-store")
        return self._send(HTTPStatus.SEE_OTHER, b"", headers={
            "Location": "/n/%s?play=1&tried=1" % note_id, "Cache-Control": "no-store"})

    def _events(self, player=False):
        """Server-Sent Events: `notes` whenever the database changed, `: ping` otherwise.

        A comment every 15 s keeps proxies (Tailscale Serve included) from closing an
        idle stream; the browser's EventSource reconnects by itself after any drop.
        `player=1` marks the stream of a tab that can take "play this note" requests.
        """
        if not player:
            return self._event_loop()
        host = (self.headers.get("Host") or "").lower()
        self.hub.add_player(host, 1)
        try:
            return self._event_loop()
        finally:
            self.hub.add_player(host, -1)

    def _event_loop(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        store = self.hub.store
        hub = self.hub
        last = store.data_version()[1]
        sig_seq = hub.seq
        self.wfile.write(b"retry: 3000\nevent: hello\ndata: {}\n\n")
        self.wfile.flush()
        idle = 0.0
        while True:
            with hub.cond:
                hub.cond.wait(timeout=1.0)
            pending = hub.signals_after(sig_seq)
            for seq, event, data in pending:
                sig_seq = seq
                payload = dict(data, req=data.get("req", seq))
                self.wfile.write(("event: %s\ndata: %s\n\n"
                                  % (event, json.dumps(payload))).encode())
            if pending:
                self.wfile.flush()
                idle = 0.0
                continue
            if self._client_gone():
                return None
            idle += 1.0
            stamp = store.data_version()[1]
            if stamp != last:
                last = stamp
                payload = json.dumps({"updated_at": stamp})
                self.wfile.write(("event: notes\ndata: %s\n\n" % payload).encode())
                self.wfile.flush()
                idle = 0.0
            elif idle >= 15:
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                idle = 0.0

    def _client_gone(self):
        """True once the browser closed the stream (tab closed): a readable socket with
        nothing to read. Checked every second so a closed hub tab stops counting as a
        player at once instead of at the next 15 s ping."""
        try:
            ready, _, _ = select.select([self.connection], [], [], 0)
            return bool(ready) and not self.connection.recv(1, socket.MSG_PEEK)
        except OSError:
            return True

    def _static(self, rel, cache="no-cache"):
        rel = os.path.normpath(rel).lstrip("/")
        if rel.startswith(".."):
            return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        path = os.path.join(WEB_DIR, rel)
        if not os.path.isfile(path):
            return self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        with open(path, "rb") as fh:
            body = fh.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith(("json", "javascript")):
            ctype += "; charset=utf-8"
        headers = {"Cache-Control": cache}
        if rel in ("index.html", "handoff.html"):
            headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                "connect-src 'self'; manifest-src 'self'; worker-src 'self'; "
                "frame-ancestors 'self' vscode-webview: https://*.vscode-cdn.net")
        if rel == "sw.js":
            headers["Service-Worker-Allowed"] = "/"
        return self._send(HTTPStatus.OK, body, ctype, headers)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # A browser closing a keep-alive socket is routine; it used to flood the log.
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def serve(cfg=None, port=None, host=None):
    cfg = cfg or config_mod.load()
    if port:
        cfg["AVH_PORT"] = str(port)
    if host:
        cfg["AVH_HOST"] = host
    Handler.hub = Hub(cfg)
    httpd = _Server((cfg["AVH_HOST"], int(cfg["AVH_PORT"])), Handler)
    sys.stderr.write("agent-voice-hub %s on %s (data: %s)\n"
                     % (__version__, config_mod.local_url(cfg), cfg["AVH_HOME"]))
    if config_mod.public_url(cfg):
        sys.stderr.write("tailnet: %s\n" % config_mod.public_url(cfg))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def serve_in_thread(cfg):
    """For tests: start on cfg's port in a daemon thread and return the server."""
    Handler.hub = Hub(cfg)
    httpd = _Server((cfg["AVH_HOST"], int(cfg["AVH_PORT"])), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
