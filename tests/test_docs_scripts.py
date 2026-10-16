"""kit/bundles/docs/scripts: Chrome detection, PDF conversion and the opener, with fakes only."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT, write

SCRIPTS = ROOT / "kit" / "bundles" / "docs" / "scripts"
CHROME = SCRIPTS / "chrome.sh"
OPEN = SCRIPTS / "open-local.sh"

FAKE_CHROME = """#!/bin/sh
# Writes whatever --print-to-pdf= or --screenshot= asks for, like headless Chrome.
for arg in "$@"; do
  case "$arg" in
    --print-to-pdf=*) printf '%%PDF-1.4 fake\\n' > "${arg#--print-to-pdf=}" ;;
    --screenshot=*) printf 'PNG' > "${arg#--screenshot=}" ;;
  esac
done
exit 0
"""


class DocsScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="docs-scripts-")
        self.tmp = Path(self._tmp.name).resolve()
        self.fake = write(self.tmp / "bin" / "fake chrome", FAKE_CHROME, mode=0o755)
        self.page = write(self.tmp / "in page.html", "<p>hi</p>\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_script(self, script: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
        e = {"PATH": "/usr/bin:/bin", "HOME": str(self.tmp), "TMPDIR": str(self.tmp)}
        e.update(env)
        return subprocess.run(["/bin/bash", str(script), *args], capture_output=True, text=True, env=e)

    def test_bash_32_syntax(self) -> None:
        for script in (CHROME, OPEN):
            p = subprocess.run(["/bin/bash", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"{script.name}: {p.stderr}")
            self.assertTrue(os.access(script, os.X_OK), f"{script.name} is not executable")

    def test_chrome_bin_wins(self) -> None:
        p = self.run_script(CHROME, "path", CHROME_BIN=str(self.fake))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), str(self.fake))

    def test_bad_chrome_bin_fails(self) -> None:
        p = self.run_script(CHROME, "path", CHROME_BIN=str(self.tmp / "missing"))
        self.assertEqual(p.returncode, 1)

    def test_pdf_and_screenshot_with_fake_chrome(self) -> None:
        pdf = self.tmp / "out file.pdf"
        p = self.run_script(CHROME, "pdf", str(self.page), str(pdf), CHROME_BIN=str(self.fake))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
        png = self.tmp / "shot.png"
        p = self.run_script(CHROME, "screenshot", str(self.page), str(png), "800,600", CHROME_BIN=str(self.fake))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(png.exists())
        leftovers = [x.name for x in self.tmp.iterdir() if x.name.startswith("chrome-profile.")]
        self.assertEqual(leftovers, [], "temporary Chrome profiles must be removed")

    def test_usage_errors(self) -> None:
        self.assertEqual(self.run_script(CHROME).returncode, 2)
        self.assertEqual(self.run_script(CHROME, "pdf", str(self.tmp / "nope.html"), "x.pdf",
                                         CHROME_BIN=str(self.fake)).returncode, 2)

    def test_open_local(self) -> None:
        self.assertEqual(self.run_script(OPEN, str(self.page), BROWSER_OPEN_CMD="true").returncode, 0)
        self.assertEqual(self.run_script(OPEN, str(self.tmp / "missing.html")).returncode, 2)
        self.assertEqual(self.run_script(OPEN).returncode, 2)


if __name__ == "__main__":
    unittest.main()
