"""voice-note.py and notify.sh, end to end against a local fake Telegram / Chat webhook,
a fake hub CLI, and (once) the real hub on a free port.

Hermetic: temp HOME, temp config, temp logs, temp AVH_HOME, and AVH_PORT set to a free
port in every run, so a hub the user runs on the default port is never touched. The only
network is 127.0.0.1. Real channels and real TTS are never called: audio comes from a
fake `say` on PATH (tests that need ffmpeg with libopus skip themselves without it), and
the browser opener is a fake that records the URL it was given."""
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from tests.helpers import ROOT

SCRIPTS = ROOT / "kit/bundles/voice/scripts"
VOICE = SCRIPTS / "voice-note.py"
NOTIFY = SCRIPTS / "notify.sh"
FAKE_TOKEN = "123456:" + "FAKE" + "telegramtokenvalue"
HUB_CLI = ROOT / "tools/voice-hub/bin/avh"
CONFIG_KEYS = ("NOTIFY_CHANNELS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GCHAT_WEBHOOK_URL",
               "GCHAT_SPACE", "GCHAT_PING_USER", "TTS_ENGINE", "TTS_API_KEY",
               "TTS_GCLOUD_ACCOUNT", "TTS_QUOTA_PROJECT", "TTS_LANG", "TTS_VOICE", "TTS_SPEED",
               "VOICE_GREETING", "VOICE_USER_NAME", "VOICE_HUB", "VOICE_HUB_CLI",
               "VOICE_HUB_OPEN", "VOICE_HUB_OPENER", "AVH_HOME", "AVH_PORT", "AVH_CONFIG",
               "AVH_PUBLIC_URL", "NOTIFY_TZ")


def have_opus():
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True)
    return b" libopus " in out.stdout


def have_say_engine():
    return bool(shutil.which("say")) and have_opus()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# A stand-in for macOS `say`: writes one second of tone (WAV bytes; ffmpeg probes the
# content, not the .aiff name), so the hub path is tested on any OS with ffmpeg.
FAKE_SAY = """#!%s
import math, struct, sys, wave
args = sys.argv[1:]
if "-o" not in args:
    sys.exit(0)
out = args[args.index("-o") + 1]
with wave.open(out, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 8.0))) for i in range(16000)))
"""

# A stand-in for tools/voice-hub/bin/avh: records every call, answers like the real CLI.
# FAKE_HUB_RUNNING=0 makes `ping` report a stopped server; FAKE_HUB_TAB=1 makes `play`
# report that an open hub tab took the note.
FAKE_HUB = """#!%s
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HUB_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\\n")
running = os.environ.get("FAKE_HUB_RUNNING", "1") == "1"
if args[0] == "ping":
    print(json.dumps({"running": running, "url": "http://127.0.0.1:9", "players": 0}))
    sys.exit(0 if running else 1)
if args[0] == "add":
    sys.stdin.read()
    print(json.dumps({"id": "n1", "urls": {"local": "http://127.0.0.1:9/n/n1"},
                      "summary": "", "agent_label": "test"}))
elif args[0] == "play":
    played = os.environ.get("FAKE_HUB_TAB") == "1"
    print(json.dumps({"running": True, "played": played, "tab": "t1" if played else ""}))
    sys.exit(0 if played else 1)
"""


class FakeApi(http.server.BaseHTTPRequestHandler):
    log = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        FakeApi.log.append({"path": self.path, "type": self.headers.get("Content-Type", ""),
                            "body": body})
        out = json.dumps({"ok": True, "result": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_a):
        pass


class VoiceScriptsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        FakeApi.log = []
        self.tmp = Path(tempfile.mkdtemp(prefix="voice-scripts-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.conf = self.tmp / "notify.env"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.hub_port = str(free_port())        # nothing listens here unless a test serves
        self.extra_env = {}
        say = self.bin / "say"
        say.write_text(FAKE_SAY % sys.executable)
        say.chmod(0o755)
        self.fake_hub = self.tmp / "avh"
        self.fake_hub.write_text(FAKE_HUB % sys.executable)
        self.fake_hub.chmod(0o755)
        self.hub_log = self.tmp / "hub.log"
        self.opener_log = self.tmp / "opened.txt"
        opener = self.tmp / "opener.sh"
        opener.write_text("#!/bin/sh\nprintf '%%s\\n' \"$@\" >> '%s'\n" % self.opener_log)
        opener.chmod(0o755)
        self.opener = opener

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, text):
        self.conf.write_text(text, encoding="utf-8")
        self.conf.chmod(0o600)

    def run_script(self, args, stdin=None, interpreter=None):
        env = {k: v for k, v in os.environ.items() if k not in CONFIG_KEYS}
        env.update({"HOME": str(self.home), "NOTIFY_CONFIG": str(self.conf),
                    "AGENT_SKELETON_STATE": str(self.tmp / "state"),
                    "VOICE_LOG": str(self.tmp / "voice.log"), "NOTIFY_LOG": str(self.tmp / "notify.log"),
                    "TELEGRAM_API_BASE": self.base, "PYTHONDONTWRITEBYTECODE": "1",
                    "AVH_HOME": str(self.tmp / "hub-data"), "AVH_PORT": self.hub_port,
                    "AVH_CONFIG": str(self.tmp / "voice-hub.env"),
                    "FAKE_HUB_LOG": str(self.hub_log),
                    "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", "")})
        env.update(self.extra_env)
        cmd = list(args)
        if interpreter:
            cmd = [interpreter] + cmd
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env,
                              cwd=str(self.tmp), timeout=120)

    # ------------------------------------------------------------------ voice-note
    def test_self_test_passes(self):
        proc = self.run_script([sys.executable, str(VOICE), "--self-test"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("0 FAIL", proc.stdout)

    @unittest.skipUnless(os.path.exists("/usr/bin/python3"), "no system python3")
    def test_self_test_on_system_python(self):
        proc = self.run_script([str(VOICE), "--self-test"], interpreter="/usr/bin/python3")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_plan_builds_the_opener_and_never_reads_code(self):
        self.config("TTS_ENGINE=none\nVOICE_USER_NAME=Ana\n")
        proc = self.run_script([sys.executable, str(VOICE), "--plan", "--source", "TERRAFORM",
                                "--title", "Plan", "Hi, this is the x agent. Done.\n\n```bash\n"
                                "terraform apply\n```\nSee https://example.com/pr/1"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Hi, Ana. This is the ", proc.stderr)
        self.assertIn("about Terraform.", proc.stderr)
        self.assertIn("The command is in the chat.", proc.stderr)
        self.assertNotIn("terraform apply", proc.stderr.split("--- spoken ---")[1])
        self.assertNotIn("example.com", proc.stderr.split("--- spoken ---")[1])
        proc = self.run_script([sys.executable, str(VOICE), "--plan", "--lang", "es", "Listo."])
        self.assertIn("Hola" + ", Ana. Soy el agente de ", proc.stderr)

    def test_channels_none_sends_nothing(self):
        self.config("NOTIFY_CHANNELS=none\nTTS_ENGINE=none\n")
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Hello there."])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no channel", proc.stderr)
        self.assertEqual(FakeApi.log, [])

    def test_hub_not_running_is_one_clear_line_and_exit_1(self):
        # Telegram credentials are present but not opted in: they must stay unused.
        self.config("TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\nTTS_ENGINE=say\n" % FAKE_TOKEN)
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Hello there."])
        self.assertEqual(proc.returncode, 1, proc.stderr)
        lines = [l for l in proc.stderr.splitlines() if "not running" in l]
        self.assertEqual(len(lines), 1, proc.stderr)
        self.assertIn("127.0.0.1:%s" % self.hub_port, lines[0])
        self.assertIn("tools/voice-hub/bin/avh " + ("service install" if sys.platform == "darwin"
                                                     else "serve"), lines[0])
        self.assertEqual(FakeApi.log, [])
        self.assertIn("failed | hub down", (self.tmp / "voice.log").read_text())

    def test_hub_cli_missing_is_an_error(self):
        self.config("VOICE_HUB_CLI=%s\nTTS_ENGINE=say\n" % (self.tmp / "absent" / "avh"))
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Hello there."])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("voice hub was not found", proc.stderr)

    def test_hub_down_with_telegram_opted_in_is_partial(self):
        self.config("NOTIFY_CHANNELS=hub,telegram\nTELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\n"
                    "TTS_ENGINE=none\n" % FAKE_TOKEN)
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Hello there."])
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(len(FakeApi.log), 1)
        self.assertIn("hub:", proc.stderr)

    def test_engine_none_delivers_text_to_telegram(self):
        self.config("NOTIFY_CHANNELS=telegram\nTELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\n"
                    "TTS_ENGINE=none\n" % FAKE_TOKEN)
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "The deploy is done."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(FakeApi.log), 1)
        self.assertTrue(FakeApi.log[0]["path"].endswith("/sendMessage"))
        self.assertIn(b"chat_id=42", FakeApi.log[0]["body"])
        self.assertNotIn(FAKE_TOKEN, proc.stderr + proc.stdout)
        log = (self.tmp / "voice.log").read_text()
        self.assertIn("sent note | kind=text to=telegram", log)
        self.assertNotIn(FAKE_TOKEN, log)
        self.assertEqual((self.tmp / "voice.log").stat().st_mode & 0o777, 0o600)

    def test_webhook_only_chat_gets_caption_and_text(self):
        hook = self.base + "/v1/spaces/X/messages?key=" + "k" * 10 + "&token=" + "t" * 12
        self.config("NOTIFY_CHANNELS=chat\nGCHAT_WEBHOOK_URL='%s'\nTTS_ENGINE=none\n" % hook)
        proc = self.run_script([sys.executable, str(VOICE), "--source", "DEPLOY", "--title", "Rel",
                                "The **release** is out."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(FakeApi.log[0]["body"])
        self.assertIn("*DEPLOY*", payload["text"])
        self.assertNotIn("t" * 12, proc.stderr + proc.stdout)

    @unittest.skipUnless(have_say_engine(), "needs macOS say and ffmpeg with libopus")
    def test_dry_run_with_say_writes_ogg_and_sends_nothing(self):
        self.config("TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\nTTS_ENGINE=say\n" % FAKE_TOKEN)
        out = self.tmp / "note.ogg"
        proc = self.run_script([sys.executable, str(VOICE), "--dry-run", "--out", str(out),
                                "--title", "Dry", "A short dry run."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out.read_bytes()[:4], b"OggS")
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        self.assertEqual(FakeApi.log, [])

    @unittest.skipUnless(have_say_engine(), "needs macOS say and ffmpeg with libopus")
    def test_say_note_reaches_fake_telegram_as_a_voice(self):
        self.config("NOTIFY_CHANNELS=telegram\nTELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\n"
                    "TTS_ENGINE=say\nTTS_SPEED=1.25\n" % FAKE_TOKEN)
        proc = self.run_script([sys.executable, str(VOICE), "--title", "Voice", "Short voice test."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(FakeApi.log[0]["path"].endswith("/sendVoice"))
        self.assertIn(b"OggS", FakeApi.log[0]["body"])
        self.assertIn("sent note | kind=audio to=telegram engine=say",
                      (self.tmp / "voice.log").read_text())

    # ------------------------------------------------------------------- hub default
    def hub_config(self, extra=""):
        self.config("VOICE_HUB_CLI=%s\nVOICE_HUB_OPENER=%s\nTTS_ENGINE=say\n"
                    "TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\n%s"
                    % (self.fake_hub, self.opener, FAKE_TOKEN, extra))

    def hub_calls(self):
        if not self.hub_log.exists():
            return []
        return [json.loads(l)[0] for l in self.hub_log.read_text().splitlines()]

    def opened(self):
        return self.opener_log.read_text().split() if self.opener_log.exists() else []

    @unittest.skipUnless(have_opus(), "needs ffmpeg with libopus")
    def test_default_goes_to_the_hub_only_and_opens_the_player(self):
        self.hub_config()
        proc = self.run_script([sys.executable, str(VOICE), "--title", "Plan", "The plan is clean."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(FakeApi.log, [], "telegram has credentials but was not opted in")
        self.assertEqual(self.hub_calls(), ["ping", "add", "play", "update"])
        self.assertEqual(self.opened(), ["http://127.0.0.1:9/n/n1?play=1"])
        self.assertIn("Markdown: [🎧 Listen: Plan](http://127.0.0.1:9/n/n1?play=1)", proc.stdout)
        self.assertIn("sent note | kind=audio to=hub engine=say", (self.tmp / "voice.log").read_text())

    @unittest.skipUnless(have_opus(), "needs ffmpeg with libopus")
    def test_open_tab_plays_it_and_no_browser_opens(self):
        self.hub_config()
        self.extra_env = {"FAKE_HUB_TAB": "1"}
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Done."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("playing in the open hub tab", proc.stderr)
        self.assertEqual(self.opened(), [])

    @unittest.skipUnless(have_opus(), "needs ffmpeg with libopus")
    def test_open_modes_always_and_never(self):
        self.hub_config("VOICE_HUB_OPEN=never\n")
        self.extra_env = {"FAKE_HUB_TAB": "1"}
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Done."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("play", self.hub_calls())
        self.assertEqual(self.opened(), [])
        proc = self.run_script([sys.executable, str(VOICE), "--open", "always", "--title", "T",
                                "Done."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.opened(), ["http://127.0.0.1:9/n/n1?play=1"])

    @unittest.skipUnless(have_opus(), "needs ffmpeg with libopus")
    def test_telegram_is_used_only_when_opted_in(self):
        self.hub_config("NOTIFY_CHANNELS=hub,telegram\nVOICE_HUB_OPEN=never\n")
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Done."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(FakeApi.log and FakeApi.log[0]["path"].endswith("/sendVoice"))
        self.assertIn("to=hub,telegram", (self.tmp / "voice.log").read_text())

    @unittest.skipUnless(have_opus() and sys.version_info >= (3, 9), "needs ffmpeg with libopus")
    def test_real_hub_on_a_free_port(self):
        self.config("VOICE_HUB_OPENER=%s\nTTS_ENGINE=say\n" % self.opener)
        env = {k: v for k, v in os.environ.items() if k not in CONFIG_KEYS}
        env.update({"HOME": str(self.home), "AVH_HOME": str(self.tmp / "hub-data"),
                    "AVH_PORT": self.hub_port, "AVH_CONFIG": str(self.tmp / "voice-hub.env")})
        server = subprocess.Popen([sys.executable, str(HUB_CLI), "serve"], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            url = "http://127.0.0.1:%s/healthz" % self.hub_port
            for _ in range(50):
                try:
                    urllib.request.urlopen(url, timeout=1).read()
                    break
                except OSError:
                    time.sleep(0.1)
            proc = self.run_script([sys.executable, str(VOICE), "--title", "Real", "It works."])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            link = [l for l in proc.stdout.splitlines() if l.startswith("🎧 Voice hub: ")][0]
            self.assertIn("127.0.0.1:%s/n/" % self.hub_port, link)
            self.assertEqual(self.opened(), [link.split(": ", 1)[1]])
            listed = subprocess.run([sys.executable, str(HUB_CLI), "list", "--json"], env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(json.loads(listed.stdout)[0]["title"], "Real")
        finally:
            server.terminate()
            server.wait(10)

    # --------------------------------------------------------------------- notify.sh
    def test_notify_without_config_prints_locally(self):
        proc = self.run_script(["/bin/bash", str(NOTIFY), "ok", "T", "<b>body</b>"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("AGENT · T\nbody", proc.stdout)
        self.assertEqual(FakeApi.log, [])

    def test_notify_none_is_silent(self):
        self.config("NOTIFY_CHANNELS=none\n")
        proc = self.run_script(["/bin/bash", str(NOTIFY), "ok", "T", "body"])
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_notify_ignores_telegram_unless_opted_in(self):
        self.config("TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\nVOICE_HUB_CLI=%s\n"
                    % (FAKE_TOKEN, self.fake_hub))
        proc = self.run_script(["/bin/bash", str(NOTIFY), "warn", "Approve", "Plan is clean.",
                                "--code-only", "make deploy"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(FakeApi.log, [])
        self.assertIn("$ make deploy", proc.stdout)
        self.assertEqual(self.hub_calls(), ["command"])
        self.assertIn("to=hub,local", (self.tmp / "notify.log").read_text())

    def test_notify_dry_run_renders_every_named_channel(self):
        proc = self.run_script(["/bin/bash", str(NOTIFY), "--dry-run", "--to", "hub,telegram,chat",
                                "--source", "TERRAFORM",
                                "ok", "T", "unclosed <b>bold & <script>", "--code", "terraform apply"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('<pre><code class="language-bash">terraform apply', proc.stderr)
        self.assertIn("<b>bold &amp; &lt;script&gt;</b>", proc.stderr)
        self.assertIn("ALSO PASTE THIS IN THE CHAT REPLY", proc.stderr)
        self.assertIn("DRY-RUN chat", proc.stderr)
        self.assertIn("DRY-RUN hub", proc.stderr)
        self.assertEqual(FakeApi.log, [])

    def test_notify_sends_and_code_only_follows(self):
        self.config("NOTIFY_CHANNELS=telegram\nTELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\n"
                    % FAKE_TOKEN)
        proc = self.run_script(["/bin/bash", str(NOTIFY), "--source", "ACTION", "warn", "Approve",
                                "Plan is clean.", "--code-only", "make deploy"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([e["path"].rsplit("/", 1)[-1] for e in FakeApi.log],
                         ["sendMessage", "sendMessage"])
        self.assertIn(b"disable_notification=false", FakeApi.log[0]["body"])
        self.assertIn(b"make+deploy", FakeApi.log[1]["body"])
        self.assertNotIn(FAKE_TOKEN, proc.stderr + proc.stdout + (self.tmp / "notify.log").read_text())

    def test_notify_warns_on_a_loose_config(self):
        self.config("TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\n" % FAKE_TOKEN)
        self.conf.chmod(0o644)
        proc = self.run_script(["/bin/bash", str(NOTIFY), "info", "T", "b"])
        self.assertIn("chmod 600", proc.stderr)


class ShellSyntaxTest(unittest.TestCase):
    def test_voice_shell_scripts_parse_with_bin_bash(self):
        bash = "/bin/bash" if os.path.exists("/bin/bash") else shutil.which("bash")
        for p in sorted((ROOT / "kit/bundles/voice").rglob("*.sh")):
            proc = subprocess.run([bash, "-n", str(p)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, "%s: %s" % (p, proc.stderr))
            self.assertTrue(os.access(p, os.X_OK), p)


if __name__ == "__main__":
    unittest.main()
