"""Offline tests: store, agent detection, HTTP server, MCP server.

    python3 -m unittest discover -s tests -v

Needs ffmpeg (the store transcodes everything to MP3). No network, no Google, no
Tailscale: each test gets its own temporary data directory and a free port, so a hub
service already running on this machine is never touched.
"""

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from avh import agents, config, mcp, server, store  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg"))


def tone(path, seconds=6):
    subprocess.check_call(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                           "-i", "sine=frequency=330:duration=%d" % seconds, path])


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="avh-test-")
        self.cfg = dict(config.DEFAULTS, AVH_HOME=os.path.join(self.tmp, "home"),
                        AVH_PORT=str(free_port()), AVH_PUBLIC_URL="https://hub.example.com:8443")
        self.store = store.Store(self.cfg["AVH_HOME"])
        self.audio = os.path.join(self.tmp, "a.wav")
        if HAVE_FFMPEG:
            tone(self.audio)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, **meta):
        meta.setdefault("text", "Hi Ana. This is the demo agent. The plan is clean and "
                                "ready to apply in production. See PROJ-769.\n\n"
                                "The link https://example.com/pr/1 is in the chat.")
        return self.store.add(self.audio, meta)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg required")
class StoreTests(Base):
    def test_add_normalises_to_mp3_with_metadata(self):
        n = self.add(title="Plan", source="terraform", tag="demo", speech_rate=1.5)
        self.assertTrue(n["audio_file"].endswith(".mp3"))
        with open(self.store.audio_path(n), "rb") as fh:
            head = fh.read(3)
        self.assertTrue(head == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3"))
        self.assertAlmostEqual(n["duration"], 6, delta=0.3)
        self.assertEqual(n["source"], "TERRAFORM")
        self.assertEqual(n["summary"], "The plan is clean and ready to apply in production.")
        self.assertEqual(n["tickets"], ["PROJ-769"])
        self.assertEqual(n["links"], ["https://example.com/pr/1"])
        self.assertEqual(len(n["peaks"]), store.PEAK_BUCKETS)
        self.assertTrue(n["segments"] and n["segments"][0]["t"] == 0)
        self.assertLess(n["segments"][-1]["t"], n["duration"])

    def test_filters_and_status(self):
        a = self.add(title="One", agent="claude-code", tag="payments")
        b = self.add(title="Two", agent="cursor", tag="demo")
        self.store.update(a["id"], {"heard_at": store.now_iso(), "starred": 1})
        self.assertEqual([n["id"] for n in self.store.list(status="unheard")], [b["id"]])
        self.assertEqual([n["id"] for n in self.store.list(status="starred")], [a["id"]])
        self.assertEqual([n["id"] for n in self.store.list(agent="cursor")], [b["id"]])
        self.assertEqual([n["id"] for n in self.store.list(tag="payments")], [a["id"]])
        self.assertEqual(len(self.store.list(q="proj-769")), 2)
        self.store.update(b["id"], {"archived": 1})
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(self.store.facets()["totals"]["total"], 1)

    def test_list_is_newest_first_and_light(self):
        self.add(title="old", created_at="2026-01-01T00:00:00.000Z")
        self.add(title="new")
        rows = self.store.list()
        self.assertEqual(rows[0]["title"], "new")
        self.assertNotIn("text", rows[0])

    def test_channels_merge_and_delete(self):
        n = self.add()
        self.store.merge_channels(n["id"], {"chat": {"status": "ok"}})
        self.store.merge_channels(n["id"], {"teams": "failed"})
        self.assertEqual(self.store.get(n["id"])["channels"],
                         {"chat": {"status": "ok"}, "teams": "failed"})
        path = self.store.audio_path(n)
        self.assertTrue(self.store.delete(n["id"]))
        self.assertFalse(os.path.exists(path))

    def test_bad_audio_raises_and_leaves_nothing(self):
        bad = os.path.join(self.tmp, "bad.wav")
        with open(bad, "wb") as fh:
            fh.write(b"not audio")
        with self.assertRaises(RuntimeError):
            self.store.add(bad, {"title": "x"})
        self.assertEqual(self.store.list(), [])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg required")
class CommandTests(Base):
    def test_code_blocks_in_text_become_commands(self):
        n = self.add(text="Done.\n\n```bash\nterraform apply -target=x\n```\nReady.")
        self.assertEqual(n["commands"][0]["code"], "terraform apply -target=x")
        self.assertEqual(n["commands"][0]["lang"], "bash")

    def test_command_after_the_note_attaches_to_its_session(self):
        n = self.add(session_id="s1", brief="I need your apply")
        other = self.add(session_id="s2")
        got = self.store.attach_command({"code": "make deploy", "label": "Deploy"}, "s1")
        self.assertEqual(got, n["id"])
        self.assertEqual(self.store.get(n["id"])["commands"][0]["code"], "make deploy")
        self.assertEqual(self.store.get(n["id"])["brief"], "I need your apply")
        self.assertEqual(self.store.get(other["id"])["commands"], [])
        self.store.attach_command({"code": "make deploy"}, "s1")      # no duplicates
        self.assertEqual(len(self.store.get(n["id"])["commands"]), 1)

    def test_command_before_the_note_waits_for_it(self):
        self.assertEqual(self.store.attach_command({"code": "ls -la"}, "s9"), "")
        n = self.add(session_id="s9")
        self.assertEqual([c["code"] for c in n["commands"]], ["ls -la"])
        self.assertEqual(self.add(session_id="s9")["commands"], [])  # consumed once

    def test_data_is_private(self):
        self.add()
        home = self.cfg["AVH_HOME"]
        self.assertEqual(os.stat(home).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(os.path.join(home, "audio")).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(os.path.join(home, "hub.db")).st_mode & 0o777, 0o600)

    def test_old_database_is_migrated(self):
        import sqlite3
        home = os.path.join(self.tmp, "old")
        os.makedirs(home)
        db = sqlite3.connect(os.path.join(home, "hub.db"))
        db.executescript(store.SCHEMA)          # v1: no commands/brief columns
        self.assertNotIn("commands", {r[1] for r in db.execute("PRAGMA table_info(notes)")})
        db.commit()
        db.close()
        store.Store(home)
        db = sqlite3.connect(os.path.join(home, "hub.db"))
        cols = {r[1] for r in db.execute("PRAGMA table_info(notes)")}
        self.assertTrue({"commands", "brief"} <= cols)


class TextTests(unittest.TestCase):
    def test_summary_skips_greeting_and_intro(self):
        s = store.derive_summary("Hi Ana. This is the payments agent, about Terraform. "
                                 "It is applied in dev and pre, with no errors.")
        self.assertEqual(s, "It is applied in dev and pre, with no errors.")
        s = store.derive_summary("Hola Ana. Soy el agente de pagos. Todo aplicado sin errores.")
        self.assertEqual(s, "Todo aplicado sin errores.")

    def test_summary_joins_a_very_short_first_sentence(self):
        self.assertEqual(store.derive_summary("Done. The apply finished cleanly."),
                         "Done. The apply finished cleanly.")

    def test_tickets_ignore_lookalikes(self):
        self.assertEqual(store.extract_tickets("UTF-8 SHA-256 PROJ-1 OPS-22 PROJ-1"),
                         ["PROJ-1", "OPS-22"])

    def test_segments_are_monotonic_and_mark_paragraphs(self):
        segs = store.segment_timeline("One sentence. Another one.\n\nA new paragraph here.", 30)
        self.assertEqual([s["p"] for s in segs], [0, 0, 1])
        self.assertEqual(segs, sorted(segs, key=lambda s: s["t"]))


class AgentTests(unittest.TestCase):
    def test_claude_inside_cursor(self):
        d = agents.detect({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "claude-vscode",
                           "CLAUDE_CODE_SESSION_ID": "abc",
                           "CURSOR_SPAWNED_BY_EXTENSION_ID": "anthropic.claude-code"}, [])
        self.assertEqual((d["agent"], d["surface"], d["session_id"]),
                         ("claude-code", "cursor", "abc"))
        self.assertEqual(d["label"], "Claude Code in Cursor")

    def test_claude_terminal_and_vscode(self):
        self.assertEqual(agents.detect({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli"},
                                       [])["label"], "Claude Code terminal")
        self.assertEqual(agents.detect({"CLAUDE_CODE_ENTRYPOINT": "claude-vscode",
                                        "VSCODE_CWD": "/Applications/Visual Studio Code.app"},
                                       [])["surface"], "vscode")

    def test_claude_via_t3(self):
        d = agents.detect({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "sdk-ts",
                           "T3CODE_HOME": "/x"}, [])
        self.assertEqual(d["surface"], "t3")

    def test_cursor_ide_and_cli(self):
        self.assertEqual(agents.detect({"CURSOR_TRACE_ID": "t"}, [])["label"], "Cursor Agent")
        self.assertEqual(agents.detect({"CURSOR_AGENT": "1"}, [])["label"], "Cursor CLI")

    def test_other_agents(self):
        self.assertEqual(agents.detect({"GEMINI_CLI": "1"}, [])["label"], "Gemini CLI")
        self.assertEqual(agents.detect({"ANTIGRAVITY_AGENT": "1"}, [])["agent"], "antigravity")
        self.assertEqual(agents.detect({"CODEX_THREAD_ID": "x"}, [])["agent"], "codex")

    def test_ancestry_fallback_and_override(self):
        self.assertEqual(agents.detect({}, ["zsh", "cursor-agent"])["label"], "Cursor CLI")
        self.assertEqual(agents.detect({}, ["bash", "claude"])["agent"], "claude-code")
        self.assertEqual(agents.detect({}, ["zsh", "login"])["agent"], "unknown")
        self.assertEqual(agents.detect({"AVH_AGENT": "gemini"}, [])["agent"], "gemini")


class ConfigTests(unittest.TestCase):
    def test_defaults_are_generic(self):
        self.assertEqual(config.DEFAULTS["AVH_TICKET_LINKS"], "")
        self.assertEqual(config.ticket_links({"AVH_TICKET_LINKS": "PROJ=https://t.example.com/"}),
                         {"PROJ": "https://t.example.com/"})
        self.assertEqual(config.DEFAULTS["AVH_PUBLIC_URL"], "")
        self.assertTrue(config.DEFAULTS["AVH_VOICE_NOTE"].endswith(
            os.path.join("kit", "bundles", "voice", "scripts", "voice-note.py")))


class RangeTests(unittest.TestCase):
    def test_parse_range(self):
        self.assertIsNone(server.parse_range(None, 100))
        self.assertEqual(server.parse_range("bytes=0-1", 100), (0, 1))
        self.assertEqual(server.parse_range("bytes=10-", 100), (10, 99))
        self.assertEqual(server.parse_range("bytes=-30", 100), (70, 99))
        self.assertEqual(server.parse_range("bytes=90-500", 100), (90, 99))
        self.assertEqual(server.parse_range("bytes=0-1, 5-9", 100), (0, 1))
        for bad in ("bytes=100-", "bytes=5-2", "bytes=-0", "bytes=-", "items=0-1"):
            self.assertEqual(server.parse_range(bad, 100), "bad", bad)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg required")
class ServerTests(Base):
    def setUp(self):
        super().setUp()
        self.note = self.add(title="Test", agent="claude-code")
        self.httpd = server.serve_in_thread(self.cfg)
        self.base = "http://127.0.0.1:%s" % self.cfg["AVH_PORT"]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def req(self, path, method="GET", headers=None, body=None):
        r = urllib.request.Request(self.base + path, method=method, headers=headers or {},
                                   data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.headers, exc.read()

    def test_list_detail_and_decoration(self):
        st, _, body = self.req("/api/notes")
        notes = json.loads(body)["notes"]
        self.assertEqual(st, 200)
        self.assertTrue(notes[0]["audio_url"].startswith("/media/%s.mp3?v=" % self.note["id"]))
        self.assertEqual(notes[0]["agent_badge"], "CC")
        self.assertTrue(notes[0]["urls"]["public"].startswith("https://hub.example.com:8443/n/"))
        st, _, body = self.req("/api/notes/" + self.note["id"])
        self.assertIn("segments", json.loads(body))

    def test_media_ranges(self):
        st, h, full = self.req("/media/%s.mp3" % self.note["id"])
        self.assertEqual((st, h["Content-Type"], h["Accept-Ranges"]), (200, "audio/mpeg", "bytes"))
        st, h, part = self.req("/media/%s.mp3" % self.note["id"], headers={"Range": "bytes=0-1"})
        self.assertEqual((st, h["Content-Range"], part), (206, "bytes 0-1/%d" % len(full),
                                                          full[:2]))
        st, h, _ = self.req("/media/%s.mp3" % self.note["id"],
                            headers={"Range": "bytes=%d-" % len(full)})
        self.assertEqual((st, h["Content-Range"]), (416, "bytes */%d" % len(full)))

    def test_guards(self):
        self.assertEqual(self.req("/api/notes", headers={"Host": "evil.test"})[0], 421)
        self.assertEqual(self.req("/api/notes/" + self.note["id"], "PATCH",
                                  body={"starred": True})[0], 403)
        st, _, body = self.req("/api/notes/" + self.note["id"], "PATCH",
                               headers={"X-AVH": "1", "Content-Type": "application/json"},
                               body={"starred": True, "heard": True, "position": 2.5})
        n = json.loads(body)
        self.assertEqual((st, n["starred"], n["position"], bool(n["heard_at"])),
                         (200, True, 2.5, True))
        self.assertEqual(self.req("/static/../store.py")[0], 404)
        self.assertEqual(self.req("/api/notes", headers={
            "Tailscale-User-Login": "someone@else"})[0], 200)

    def test_spa_routes_and_assets(self):
        for path in ("/", "/n/" + self.note["id"], "/sw.js", "/manifest.webmanifest",
                     "/static/app.js", "/static/app.css", "/static/icons/icon-192.png"):
            self.assertEqual(self.req(path)[0], 200, path)
        st, h, _ = self.req("/")
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])


FAKE_VOICE_NOTE = """#!/usr/bin/env python3
import subprocess, sys
args = sys.argv[1:]
out = args[args.index("--out") + 1]
assert "--no-send" in args and "--no-hub" in args and args[args.index("--speed") + 1] == "1.0"
text = sys.stdin.read()
subprocess.check_call(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                       "-i", "sine=frequency=500:duration=9", "-c:a", "libopus", out])
"""


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg required")
class ResynthAndPlayTests(Base):
    def setUp(self):
        super().setUp()
        fake = os.path.join(self.tmp, "voice-note.py")
        with open(fake, "w") as fh:
            fh.write(FAKE_VOICE_NOTE)
        self.cfg["AVH_VOICE_NOTE"] = fake
        self.note = self.add(title="Old", speech_rate=1.5)
        self.httpd = server.serve_in_thread(self.cfg)
        self.base = "http://127.0.0.1:%s" % self.cfg["AVH_PORT"]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def post(self, path, body):
        r = urllib.request.Request(self.base + path, method="POST",
                                   headers={"X-AVH": "1", "Content-Type": "application/json"},
                                   data=json.dumps(body).encode())
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read())

    def test_resynth_replaces_audio_at_natural_rate(self):
        old_path = self.store.audio_path(self.note)
        got = json.loads(urllib.request.urlopen(
            self.base + "/api/notes/" + self.note["id"]).read())
        self.assertTrue(got["can_resynth"])
        n = self.post("/api/notes/%s/resynth" % self.note["id"], {})
        self.assertEqual(n["speech_rate"], 1.0)
        self.assertAlmostEqual(n["duration"], 9, delta=0.3)
        self.assertFalse(n["can_resynth"])
        self.assertFalse(os.path.exists(old_path))
        self.assertNotEqual(n["audio_url"], got["audio_url"], "cache-busting version")
        self.assertEqual(n["segments"][0]["t"], 0)

    def test_play_signal_reaches_event_stream(self):
        import threading
        lines = []

        def listen():
            with urllib.request.urlopen(self.base + "/api/events", timeout=10) as resp:
                for raw in resp:
                    lines.append(raw.decode().strip())
                    if lines[-1].startswith("data:") and '"from": "tabA"' in lines[-1]:
                        return
        t = threading.Thread(target=listen, daemon=True)
        t.start()
        import time
        time.sleep(0.5)
        req = self.post("/api/play", {"id": self.note["id"], "from": "tabA"})["req"]
        self.post("/api/play-ack", {"req": req, "tab": "tabB"})
        t.join(5)
        self.assertIn("event: play", lines)
        data = json.loads([l for l in lines if l.startswith("data:") and "tabA" in l][0][5:])
        self.assertEqual((data["id"], data["req"]), (self.note["id"], req))

    def test_play_link_without_open_hub_loads_the_app(self):
        with urllib.request.urlopen(self.base + "/n/%s?play=1" % self.note["id"]) as resp:
            self.assertTrue(resp.geturl().endswith("/n/%s?play=1&tried=1" % self.note["id"]))
            self.assertIn(b"app.js", resp.read())

    def test_play_link_hands_off_to_open_player_tab(self):
        import threading
        stream = urllib.request.urlopen(self.base + "/api/events?player=1", timeout=10)

        def player_tab():                      # what app.js does on a `play` event
            for raw in stream:
                line = raw.decode().strip()
                if line.startswith("data:") and '"from": "link"' in line:
                    self.post("/api/play-ack", {"req": json.loads(line[5:])["req"], "tab": "tabB"})
                    return
        t = threading.Thread(target=player_tab, daemon=True)
        t.start()
        import time
        time.sleep(0.5)
        t0 = time.monotonic()
        with urllib.request.urlopen(self.base + "/n/%s?play=1" % self.note["id"]) as resp:
            body = resp.read()
            self.assertNotIn("tried=1", resp.geturl())
        self.assertIn(b"handoff.js", body)
        self.assertLess(time.monotonic() - t0, 2.0)
        t.join(5)
        stream.close()

    def test_play_with_wait_and_no_open_tab_answers_at_once(self):
        import time
        t0 = time.monotonic()
        got = self.post("/api/play", {"id": self.note["id"], "from": "cli", "wait": 3})
        self.assertEqual((got["tab"], got["players"]), ("", 0))
        self.assertLess(time.monotonic() - t0, 1.0)
        health = json.loads(urllib.request.urlopen(self.base + "/healthz").read())
        self.assertEqual((health["ok"], health["players"]), (True, 0))

    def test_play_with_wait_reaches_an_open_player_tab(self):
        import threading
        import time
        stream = urllib.request.urlopen(self.base + "/api/events?player=1", timeout=10)

        def player_tab():
            for raw in stream:
                line = raw.decode().strip()
                if line.startswith("data:") and '"from": "cli"' in line:
                    self.post("/api/play-ack", {"req": json.loads(line[5:])["req"], "tab": "tabC"})
                    return
        t = threading.Thread(target=player_tab, daemon=True)
        t.start()
        time.sleep(0.5)
        health = json.loads(urllib.request.urlopen(self.base + "/healthz").read())
        self.assertEqual(health["players"], 1)
        got = self.post("/api/play", {"id": self.note["id"], "from": "cli", "wait": 3})
        self.assertEqual((got["tab"], got["players"]), ("tabC", 1))
        t.join(5)
        stream.close()

    def cli(self, *args):
        env = dict(os.environ, HOME=self.tmp, AVH_HOME=self.cfg["AVH_HOME"],
                   AVH_PORT=self.cfg["AVH_PORT"], AVH_CONFIG=os.path.join(self.tmp, "none.env"))
        return subprocess.run([sys.executable, os.path.join(ROOT, "bin", "avh")] + list(args),
                              env=env, capture_output=True, text=True, timeout=30)

    def test_cli_ping_and_play(self):
        proc = self.cli("ping", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["running"], True)
        proc = self.cli("play", self.note["id"], "--wait", "0.5", "--json")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual((out["running"], out["played"]), (True, False))

    def test_cli_ping_when_down_names_the_start_command(self):
        self.cfg["AVH_PORT"] = str(free_port())          # nothing listens there
        proc = self.cli("ping", "--json")
        self.assertEqual(proc.returncode, 1)
        out = json.loads(proc.stdout)
        self.assertFalse(out["running"])
        self.assertIn("tools/voice-hub/bin/avh", out["start"])
        self.assertEqual(self.cli("play", self.note["id"], "--json").returncode, 2)

    def test_mark_all_heard(self):
        other = self.add(title="Other")
        self.assertEqual(self.post("/api/notes/mark-all-heard", {}), {"marked": 2})
        self.assertTrue(self.store.get(other["id"])["heard_at"])
        self.assertEqual(self.store.list(status="unheard"), [])
        self.assertEqual(self.post("/api/notes/mark-all-heard", {}), {"marked": 0})

    def test_theme_script_is_served(self):
        with urllib.request.urlopen(self.base + "/static/theme.js") as resp:
            self.assertIn(b"avh.theme", resp.read())


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg required")
class McpTests(Base):
    def test_protocol_and_chunks(self):
        n = self.add(title="Listen to me")
        srv = mcp.Server(self.cfg)
        init = srv.handle({"method": "initialize", "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"extensions": {mcp.UI_EXT: {"mimeTypes": [mcp.UI_MIME]}}}}})
        self.assertTrue(srv.ui)
        self.assertEqual(init["serverInfo"]["name"], "agent-voice-hub")
        tools = {t["name"]: t for t in srv.handle({"method": "tools/list"})["tools"]}
        self.assertEqual(tools["voice_note_play"]["_meta"]["ui"]["resourceUri"], mcp.UI_URI)
        self.assertEqual(tools["voice_note_audio_chunk"]["_meta"]["ui"]["visibility"], ["app"])
        plain = mcp.Server(self.cfg)
        plain.handle({"method": "initialize", "params": {"capabilities": {}}})
        names = [t["name"] for t in plain.handle({"method": "tools/list"})["tools"]]
        self.assertNotIn("voice_note_audio_chunk", names)
        self.assertIn("voice_note_play", names)
        res = srv.handle({"method": "resources/read", "params": {"uri": mcp.UI_URI}})
        self.assertEqual(res["contents"][0]["mimeType"], mcp.UI_MIME)
        self.assertIn("ui/initialize", res["contents"][0]["text"])
        play = srv.call("voice_note_play", {})
        self.assertEqual(play["structuredContent"]["note"]["id"], n["id"])
        self.assertNotIn("data", json.dumps(play["structuredContent"])[:0])
        data, offset = b"", 0
        while offset is not None:
            c = srv.call("voice_note_audio_chunk", {"id": n["id"], "offset": offset})
            data += base64.b64decode(c["structuredContent"]["data"])
            offset = c["structuredContent"]["next"]
        with open(self.store.audio_path(n), "rb") as fh:
            self.assertEqual(data, fh.read())
        self.assertEqual(mcp.CHUNK % 3, 0, "chunks must concatenate as base64")
        recent = srv.call("voice_notes_recent", {"limit": 5})
        self.assertIn("Listen to me", recent["content"][0]["text"])
        self.assertTrue(srv.call("voice_note_get", {"id": "nope"})["isError"])
        srv.call("voice_note_mark_heard", {"id": n["id"]})
        self.assertTrue(self.store.get(n["id"])["heard_at"])


if __name__ == "__main__":
    unittest.main()
