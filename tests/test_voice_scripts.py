"""voice-note.py and notify.sh, end to end against a local fake Telegram / Chat webhook.

Hermetic: temp HOME, temp config, temp logs; the only network is 127.0.0.1. Real
channels and real TTS are never called (the say engine is local, and its tests are
skipped where `say` or ffmpeg with libopus is missing)."""
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tests.helpers import ROOT

SCRIPTS = ROOT / "kit/bundles/voice/scripts"
VOICE = SCRIPTS / "voice-note.py"
NOTIFY = SCRIPTS / "notify.sh"
FAKE_TOKEN = "123456:" + "FAKE" + "telegramtokenvalue"
CONFIG_KEYS = ("NOTIFY_CHANNELS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GCHAT_WEBHOOK_URL",
               "GCHAT_SPACE", "GCHAT_PING_USER", "TTS_ENGINE", "TTS_API_KEY",
               "TTS_GCLOUD_ACCOUNT", "TTS_QUOTA_PROJECT", "TTS_LANG", "TTS_VOICE", "TTS_SPEED",
               "VOICE_GREETING", "VOICE_USER_NAME", "VOICE_HUB", "VOICE_HUB_CLI")


def have_say_engine():
    if not (shutil.which("say") and shutil.which("ffmpeg")):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True)
    return b" libopus " in out.stdout


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
                    "TELEGRAM_API_BASE": self.base, "PYTHONDONTWRITEBYTECODE": "1"})
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

    def test_nothing_configured_sends_nothing(self):
        self.config("TTS_ENGINE=none\n")
        proc = self.run_script([sys.executable, str(VOICE), "--title", "T", "Hello there."])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no channel configured", proc.stderr)
        self.assertEqual(FakeApi.log, [])

    def test_engine_none_delivers_text_to_telegram(self):
        self.config("TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\nTTS_ENGINE=none\n" % FAKE_TOKEN)
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
        self.config("GCHAT_WEBHOOK_URL='%s'\nTTS_ENGINE=none\n" % hook)
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
        self.config("TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\nTTS_ENGINE=say\nTTS_SPEED=1.25\n"
                    % FAKE_TOKEN)
        proc = self.run_script([sys.executable, str(VOICE), "--title", "Voice", "Short voice test."])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(FakeApi.log[0]["path"].endswith("/sendVoice"))
        self.assertIn(b"OggS", FakeApi.log[0]["body"])
        self.assertIn("sent note | kind=audio to=telegram engine=say",
                      (self.tmp / "voice.log").read_text())

    # --------------------------------------------------------------------- notify.sh
    def test_notify_noop_without_config(self):
        proc = self.run_script(["/bin/bash", str(NOTIFY), "ok", "T", "body"])
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        self.assertEqual(FakeApi.log, [])

    def test_notify_dry_run_renders_both_channels(self):
        proc = self.run_script(["/bin/bash", str(NOTIFY), "--dry-run", "--source", "TERRAFORM",
                                "ok", "T", "unclosed <b>bold & <script>", "--code", "terraform apply"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('<pre><code class="language-bash">terraform apply', proc.stderr)
        self.assertIn("<b>bold &amp; &lt;script&gt;</b>", proc.stderr)
        self.assertIn("ALSO PASTE THIS IN THE CHAT REPLY", proc.stderr)
        self.assertIn("DRY-RUN chat", proc.stderr)
        self.assertEqual(FakeApi.log, [])

    def test_notify_sends_and_code_only_follows(self):
        self.config("TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=42\n" % FAKE_TOKEN)
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
