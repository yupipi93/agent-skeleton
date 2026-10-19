"""The voice bundle's Stop hook, driven with crafted transcripts. Hermetic: temp HOME,
temp config, temp log; nothing touches a real channel."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

HOOK = ROOT / "kit/bundles/voice/scripts/voice-note-hook.py"
CONFIG_KEYS = ("NOTIFY_CHANNELS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GCHAT_WEBHOOK_URL",
               "GCHAT_SPACE", "VOICE_HUB", "VOICE_HUB_OPEN", "VOICE_HUB_CLI", "VOICE_HOOK_LONG_SECONDS", "VOICE_HOOK_TOOL_CALLS",
               "VOICE_HOOK_REPLY_CHARS", "VOICE_HOOK_OPTOUT", "TTS_ENGINE")
T0 = datetime.datetime(2026, 1, 5, 9, 0, 0, tzinfo=datetime.timezone.utc)


def claude_transcript(path, user_text, calls=0, chars=0, cmd="", minutes=0, extra_tools=()):
    rows = [{"type": "user", "uuid": "u1", "timestamp": T0.isoformat(),
             "message": {"content": user_text}}]
    blocks = []
    for i in range(calls):
        blocks.append({"type": "tool_use", "name": "Bash", "id": "t%d" % i,
                       "input": {"command": cmd if i == 0 and cmd else "ls"}})
    for name in extra_tools:
        blocks.append({"type": "tool_use", "name": name, "id": name, "input": {}})
    if chars:
        blocks.append({"type": "text", "text": "x" * chars})
    rows.append({"type": "assistant", "uuid": "a1",
                 "timestamp": (T0 + datetime.timedelta(minutes=minutes)).isoformat(),
                 "message": {"content": blocks}})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="voice-hook-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.conf = self.tmp / "notify.env"
        self.conf.write_text("TELEGRAM_BOT_TOKEN=123:fake\nTELEGRAM_CHAT_ID=42\n", encoding="utf-8")
        self.conf.chmod(0o600)
        self.log = self.tmp / "voice.log"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, event, client="claude", conf=None, log=None):
        env = {k: v for k, v in os.environ.items() if k not in CONFIG_KEYS}
        env.update({"HOME": str(self.home), "NOTIFY_CONFIG": str(conf or self.conf),
                    "VOICE_LOG": str(log or self.log),
                    "VOICE_HOOK_STATE": str(self.tmp / "state"), "PYTHONDONTWRITEBYTECODE": "1"})
        return subprocess.run([sys.executable, str(HOOK), "--client", client],
                              input=json.dumps(event), capture_output=True, text=True, env=env,
                              timeout=30)

    def code(self, transcript, session, **kw):
        return self.run_hook({"transcript_path": str(transcript), "session_id": session},
                             **kw).returncode

    def t(self, name, *a, **kw):
        return claude_transcript(self.tmp / name, *a, **kw)

    # ---------------------------------------------------------------- signals
    def test_quiet_turn_is_left_alone(self):
        self.assertEqual(self.code(self.t("s.jsonl", "fix the typo", 2, 40), "s1"), 0)

    def test_each_signal_blocks(self):
        cases = {
            "long": self.t("long.jsonl", "apply it", 2, 40, minutes=9),
            "complex": self.t("cx.jsonl", "apply it", 20, 40, minutes=1),
            "wall": self.t("wall.jsonl", "apply it", 2, 1500, minutes=1),
            "command": self.t("cmd.jsonl", "apply it", 3, 40, minutes=1,
                              cmd="kit/bundles/voice/scripts/notify.sh --source GCP info T b --code 'x'"),
            "subagent": self.t("sub.jsonl", "apply it", 1, 40, extra_tools=("Agent",)),
            "question": self.t("ask.jsonl", "apply it", 1, 40, extra_tools=("AskUserQuestion",)),
        }
        for name, path in cases.items():
            proc = self.run_hook({"transcript_path": str(path), "session_id": "s-" + name})
            self.assertEqual(proc.returncode, 2, name)
            self.assertIn("voice-note.py", proc.stderr)
            self.assertIn("no audio", proc.stderr)

    def test_thresholds_come_from_config(self):
        conf = self.tmp / "loose.env"
        conf.write_text("TELEGRAM_BOT_TOKEN=1:x\nTELEGRAM_CHAT_ID=1\nVOICE_HOOK_TOOL_CALLS=50\n"
                        "VOICE_HOOK_REPLY_CHARS=0\n", encoding="utf-8")
        path = self.t("cx.jsonl", "apply it", 20, 5000, minutes=1)
        self.assertEqual(self.code(path, "s-loose", conf=conf), 0)

    # ------------------------------------------------------------- compliance
    def test_a_delivered_note_satisfies_the_hook(self):
        local = T0.astimezone().replace(tzinfo=None) + datetime.timedelta(minutes=5)
        self.log.write_text("%s sent note | kind=audio to=telegram\n" % local.strftime("%Y-%m-%d %H:%M:%S"))
        path = self.t("spoke.jsonl", "apply it", 20, 1500, minutes=9,
                      cmd="kit/bundles/voice/scripts/voice-note.py --source TERRAFORM --title 'Apply' "
                          "'First paragraph.\n\nSecond paragraph.'")
        self.assertEqual(self.code(path, "s-spoke"), 0)

    def test_a_call_without_delivery_still_blocks(self):
        old = T0.astimezone().replace(tzinfo=None) - datetime.timedelta(days=1)
        self.log.write_text("%s sent note | kind=audio\n" % old.strftime("%Y-%m-%d %H:%M:%S"))
        path = self.t("stale.jsonl", "apply it", 20, 1500, minutes=9,
                      cmd="kit/bundles/voice/scripts/voice-note.py --title T 'x'")
        proc = self.run_hook({"transcript_path": str(path), "session_id": "s-stale"})
        self.assertEqual(proc.returncode, 2)
        self.assertIn("no delivery", proc.stderr)

    def test_missing_log_fails_open(self):
        path = self.t("nolog.jsonl", "apply it", 20, 1500, minutes=9,
                      cmd="kit/bundles/voice/scripts/voice-note.py --title T 'x'")
        self.assertEqual(self.code(path, "s-nolog", log=self.tmp / "absent.log"), 0)

    def test_non_sends_do_not_count(self):
        for i, cmd in enumerate(["kit/bundles/voice/scripts/voice-note.py --dry-run --title T 'x'",
                                 "kit/bundles/voice/scripts/voice-note.py --plan 'x'",
                                 'VOICE="/x/voice-note.py"; echo ok',
                                 "cat > f <<'EOF'\nvoice-note.py --title T 'x'\nEOF"]):
            path = self.t("n%d.jsonl" % i, "apply it", 20, 1500, minutes=9, cmd=cmd)
            self.assertEqual(self.code(path, "s-n%d" % i, log=self.tmp / "absent.log"), 2, cmd)

    # ---------------------------------------------------------------- ways out
    def test_opt_out_phrase(self):
        path = self.t("opt.jsonl", "apply it, no audio please", 20, 1500, minutes=9)
        self.assertEqual(self.code(path, "s-opt"), 0)
        conf = self.tmp / "es.env"
        conf.write_text("TELEGRAM_BOT_TOKEN=1:x\nTELEGRAM_CHAT_ID=1\nVOICE_HOOK_OPTOUT=sin audio,quiet\n")
        path = self.t("opt2.jsonl", "aplica, sin audio", 20, 1500, minutes=9)
        self.assertEqual(self.code(path, "s-opt2", conf=conf), 0)

    def test_gives_up_after_three_blocks(self):
        path = self.t("strike.jsonl", "apply it", 20, 1500, minutes=9)
        self.assertEqual([self.code(path, "s-strike") for _ in range(4)], [2, 2, 2, 0])

    def test_inert_until_the_bundle_is_configured(self):
        path = self.t("inert.jsonl", "apply it", 20, 1500, minutes=9)
        # No notify.env yet: a new user is never blocked, although the hub is the default.
        self.assertEqual(self.code(path, "s-inert2", conf=self.tmp / "absent.env"), 0)
        unready = self.tmp / "unready.env"
        unready.write_text("NOTIFY_CHANNELS=telegram\nTELEGRAM_BOT_TOKEN=1:x\nTELEGRAM_CHAT_ID=\n")
        self.assertEqual(self.code(path, "s-inert", conf=unready), 0)
        none = self.tmp / "none.env"
        none.write_text("NOTIFY_CHANNELS=none\nTELEGRAM_BOT_TOKEN=1:x\nTELEGRAM_CHAT_ID=1\n")
        self.assertEqual(self.code(path, "s-inert3", conf=none), 0)
        off = self.tmp / "off.env"
        off.write_text("VOICE_HUB=off\n")
        self.assertEqual(self.code(path, "s-inert4", conf=off), 0)

    def test_a_hub_delivery_satisfies_the_hook(self):
        local = T0.astimezone().replace(tzinfo=None) + datetime.timedelta(minutes=5)
        self.log.write_text("%s sent note | kind=audio to=hub engine=say\n"
                            % local.strftime("%Y-%m-%d %H:%M:%S"))
        conf = self.tmp / "hub.env"
        conf.write_text("NOTIFY_CHANNELS=hub\n")
        path = self.t("hub.jsonl", "apply it", 20, 1500, minutes=9,
                      cmd="kit/bundles/voice/scripts/voice-note.py --title T 'Done.'")
        self.assertEqual(self.code(path, "s-hub", conf=conf), 0)

    def test_chat_or_hub_alone_enforce(self):
        path = self.t("alone.jsonl", "apply it", 20, 1500, minutes=9)
        for i, text in enumerate(["NOTIFY_CHANNELS=chat\n"
                                  "GCHAT_WEBHOOK_URL='https://chat.example.com/x?key=a&token=b'\n",
                                  "NOTIFY_CHANNELS=hub\n", "# defaults: the hub\n"]):
            conf = self.tmp / ("alone%d.env" % i)
            conf.write_text(text)
            self.assertEqual(self.code(path, "s-alone%d" % i, conf=conf), 2, text)

    def test_bad_input_fails_open(self):
        broken = self.tmp / "broken.jsonl"
        broken.write_text("not json\n")
        self.assertEqual(self.code(broken, "s-b"), 0)
        self.assertEqual(self.code(self.tmp / "missing.jsonl", "s-m"), 0)
        env = dict(os.environ, HOME=str(self.home), NOTIFY_CONFIG=str(self.conf))
        proc = subprocess.run([sys.executable, str(HOOK), "--client", "claude", "--unknown"],
                              input="garbage", capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0)

    # ------------------------------------------------------------ other clients
    def test_cursor_gets_a_followup_message(self):
        rows = [{"role": "user", "message": {"content": [{"type": "text", "text": "do it"}]}},
                {"role": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Shell", "input": {"command": "ls"}}] * 20}}]
        path = self.tmp / "cursor.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        proc = self.run_hook({"transcript_path": str(path), "conversation_id": "c1",
                              "status": "completed", "loop_count": 0}, client="cursor")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("voice-note.py", json.loads(proc.stdout)["followup_message"])
        proc = self.run_hook({"transcript_path": str(path), "conversation_id": "c2",
                              "status": "completed", "loop_count": 3}, client="cursor")
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        proc = self.run_hook({"transcript_path": str(path), "conversation_id": "c3",
                              "status": "aborted"}, client="cursor")
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))

    def test_gemini_transcript_and_event_fallback(self):
        doc = {"sessionId": "g", "messages": [
            {"type": "user", "content": "deploy it", "timestamp": T0.isoformat()},
            {"type": "gemini", "content": "ok", "timestamp": (T0 + datetime.timedelta(minutes=1)).isoformat(),
             "toolCalls": [{"name": "run_shell_command", "args": {"command": "ls"}}] * 16}]}
        path = self.tmp / "gemini.json"
        path.write_text(json.dumps(doc))
        proc = self.run_hook({"transcript_path": str(path), "session_id": "g1"}, client="gemini")
        self.assertEqual(proc.returncode, 2)
        (self.tmp / "empty.log").write_text("")
        proc = self.run_hook({"session_id": "g2", "prompt": "explain", "prompt_response": "y" * 2000},
                             client="gemini", log=self.tmp / "empty.log")
        self.assertEqual(proc.returncode, 2)
        recent = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.write_text("%s sent note | kind=say\n" % recent)
        proc = self.run_hook({"session_id": "g3", "prompt": "explain", "prompt_response": "y" * 2000},
                             client="gemini")
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
