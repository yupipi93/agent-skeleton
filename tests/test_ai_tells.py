"""kit/bundles/style/scripts/ai-tells.py on machine-written and human-written drafts."""
from __future__ import annotations

import subprocess
import sys
import unittest

from tests.helpers import ROOT

SCRIPT = ROOT / "kit" / "bundles" / "style" / "scripts" / "ai-tells.py"
EM_DASH = "\u2014"

MACHINE = """## Key Benefits Of The New Gateway

The new gateway serves as a pivotal component in our evolving landscape, underscoring our
commitment to robust security. It's not just a proxy, it's a platform. Experts argue it is
a testament to modern design. It's important to note that results may vary.

- **Security:** robust authentication.
- **Performance:** meticulous caching.
- **Reliability:** enhanced failover.

In conclusion, the gateway is ready. Let me know if you have questions.
"""

HUMAN = """## Gateway migration

The gateway now runs on Cloud Run in all three environments. Dev and pre moved on Monday;
pro moved last night at 22:00 with no errors.

Tokens now expire after one hour instead of twelve. Clients that cache a token for longer
will get a 401 and must refresh it.

Rollback is one command: point the DNS record back at the VM.
"""

SPANISH = """No se trata solo de un cambio técnico, sino de una transformación, consolidando
nuestra posición. Cabe destacar que desempeña un papel fundamental. En resumen, está listo.
"""


class AiTellsTest(unittest.TestCase):
    def run_script(self, text: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=text,
                              capture_output=True, text=True)

    def test_human_text_is_clean(self):
        proc = self.run_script(HUMAN)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("clean", proc.stdout)

    def test_machine_text_warns_on_each_family(self):
        proc = self.run_script(MACHINE)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        for category in ("puffery", "parallelism", "participle", "weasel", "didactic",
                         "chatter", "vocabulary", "format"):
            self.assertIn(category, proc.stdout)
        self.assertIn("Title Case heading", proc.stdout)
        self.assertIn("inline-header list", proc.stdout)

    def test_hard_findings_exit_2(self):
        for text in ("Certainly! The job is done.",
                     "See the docs oaicite for details.",
                     "Signed, [Your Name]",
                     "Released on 2026-XX-XX.",
                     "As of my last knowledge update, it was in beta.",
                     "Done %s mostly." % EM_DASH):
            proc = self.run_script(text)
            self.assertEqual(proc.returncode, 2, (text, proc.stdout))

    def test_spanish_tells(self):
        proc = self.run_script(SPANISH, "--lang", "es")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        for label in ("no solo X sino Y", "gerundio de cola", "didactic disclaimer",
                      "inflated significance", "summary opener"):
            self.assertIn(label, proc.stdout)

    def test_lang_filter(self):
        self.assertEqual(self.run_script(SPANISH, "--lang", "en").returncode, 0)

    def test_code_and_quotes_are_skipped(self):
        text = "Run this:\n\n```\necho 'serves as a testament %s crucial'\n```\n\n> Experts argue.\n" % EM_DASH
        self.assertEqual(self.run_script(text).returncode, 0)

    def test_artifacts_found_inside_code(self):
        text = "```\nsee turn0search3\n```\n"
        self.assertEqual(self.run_script(text).returncode, 2)

    def test_single_vocabulary_word_is_only_a_note(self):
        proc = self.run_script("The cluster is robust enough for the load we measured last week.")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("NOTE", proc.stdout)

    def test_missing_file_is_usage_error(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "/nonexistent/draft.md"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 64)


if __name__ == "__main__":
    unittest.main()
