"""The vendored voice hub: its own test suite (temp data dir, free ports) and the rendering
of the voice bundle's Stop hook for every tool."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT, RepoTestCase

HUB = ROOT / "tools" / "voice-hub"


class HubSuiteTest(unittest.TestCase):
    def test_hub_unit_tests_pass(self):
        with tempfile.TemporaryDirectory(prefix="voice-hub-home-") as home:
            env = dict(os.environ, HOME=home, PYTHONDONTWRITEBYTECODE="1")
            env.pop("AVH_HOME", None)
            env.pop("AVH_PORT", None)
            proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                                  cwd=str(HUB), env=env, capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])

    def test_hub_cli_runs(self):
        with tempfile.TemporaryDirectory(prefix="voice-hub-home-") as home:
            env = dict(os.environ, HOME=home, AVH_HOME=os.path.join(home, "data"))
            proc = subprocess.run([sys.executable, str(HUB / "bin" / "avh"), "list", "--json"],
                                  env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout), [])
            self.assertEqual(os.stat(os.path.join(home, "data")).st_mode & 0o777, 0o700)


class VoiceHookRenderTest(RepoTestCase):
    def test_stop_hook_renders_for_every_tool(self):
        self.run_cli("enable", "voice")
        r = self.repo
        cmd = "kit/bundles/voice/scripts/voice-note-hook.py"
        claude = json.loads((r / ".claude/settings.json").read_text())
        handler = claude["hooks"]["Stop"][0]["hooks"][0]
        self.assertIn('"$CLAUDE_PROJECT_DIR"/' + cmd + " --client claude", handler["command"])
        self.assertEqual(handler["timeout"], 20)
        cursor = json.loads((r / ".cursor/hooks.json").read_text())
        self.assertEqual(cursor["hooks"]["stop"][0]["command"], "./" + cmd + " --client cursor")
        gemini = json.loads((r / ".gemini/settings.json").read_text())
        g = gemini["hooks"]["AfterAgent"][0]["hooks"][0]
        self.assertEqual(g["timeout"], 20000)
        self.assertIn("--client gemini", g["command"])
        agents = json.loads((r / ".agents/hooks.json").read_text())
        self.assertIn("--client antigravity", json.dumps(agents))
        self.assertTrue((r / ".claude/skills/voice-summary/SKILL.md").exists())
        self.assertTrue((r / ".claude/rules/notify-on-long-tasks.md").exists())
        self.run_cli("disable", "voice")
        self.assertFalse((r / ".claude/skills/voice-summary").exists())
        claude = json.loads((r / ".claude/settings.json").read_text())
        self.assertNotIn("Stop", claude.get("hooks", {}))


if __name__ == "__main__":
    unittest.main()
