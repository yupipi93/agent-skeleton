"""kit/bundles/style/scripts/text-budget.py: character budgets for text people read."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT

SCRIPT = ROOT / "kit" / "bundles" / "style" / "scripts" / "text-budget.py"


class TextBudgetTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)

    def run_script(self, text: str, *args: str, env: dict | None = None):
        full_env = {k: v for k, v in os.environ.items() if not k.startswith("TEXT_BUDGET_")}
        full_env["HOME"] = self.home.name
        full_env.update(env or {})
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=text,
                              capture_output=True, text=True, env=full_env)

    def test_short_chat_passes(self):
        proc = self.run_script("Hola, **aplicado** en pre.", "--kind", "chat")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("ok, chat", proc.stdout)

    def test_long_chat_is_blocked_with_the_cut(self):
        proc = self.run_script("palabra " * 40, "--kind", "chat")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("319/200", proc.stdout)
        self.assertIn("Cut 119", proc.stdout)

    def test_code_urls_and_markup_are_free(self):
        text = ("**Hecho**: ver [el PR](https://example.com/pr/1) y https://example.com/x\n\n"
                "```bash\n" + "echo hi\n" * 100 + "```\n- uno\n- dos\n")
        proc = self.run_script(text, "--kind", "notify")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("ok, notify 26/160", proc.stdout)

    def test_env_and_config_file_override(self):
        proc = self.run_script("x" * 50, "--kind", "chat", env={"TEXT_BUDGET_CHAT": "40"})
        self.assertEqual(proc.returncode, 2)
        cfg = os.path.join(self.home.name, ".config", "agent-skeleton")
        os.makedirs(cfg)
        with open(os.path.join(cfg, "style.env"), "w", encoding="utf-8") as fh:
            fh.write("TEXT_BUDGET_CHAT=60\n")
        proc = self.run_script("x" * 50, "--kind", "chat")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        listing = self.run_script("", "--list")
        self.assertIn("chat        60  config", listing.stdout)

    def test_max_and_usage(self):
        self.assertEqual(self.run_script("abcdef", "--max", "5").returncode, 2)
        self.assertEqual(self.run_script("abc").returncode, 64)


if __name__ == "__main__":
    unittest.main()
