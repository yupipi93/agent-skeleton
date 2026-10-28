"""kit/bundles/docs/scripts: Chrome detection, PDF conversion and the opener, with fakes only."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.helpers import ROOT, write

SCRIPTS = ROOT / "kit" / "bundles" / "docs" / "scripts"
CHROME = SCRIPTS / "chrome.sh"
OPEN = SCRIPTS / "open-local.sh"
RICH = SCRIPTS / "rich-message.py"

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
        for script in (CHROME, OPEN, SCRIPTS / "install-editor-browser.sh"):
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

    def fake_openers(self) -> tuple[str, Path]:
        """Fake `open` and `xdg-open` that record their argument; returns (PATH, log)."""
        log = self.tmp / "opened.log"
        for name in ("open", "xdg-open"):
            write(self.tmp / "fakebin" / name, f'#!/bin/sh\nprintf "%s\\n" "$1" >> "{log}"\n', mode=0o755)
        return f"{self.tmp / 'fakebin'}:/usr/bin:/bin", log

    def opened(self, log: Path) -> str:
        for _ in range(50):  # xdg-open runs in the background
            if log.exists() and log.read_text():
                return log.read_text().strip()
            time.sleep(0.05)
        return ""

    def test_open_local_editor_browser(self) -> None:
        path, log = self.fake_openers()
        (self.tmp / ".cursor" / "extensions" / "agent-skeleton.editor-browser-open-0.1.0").mkdir(parents=True)
        p = self.run_script(OPEN, str(self.page), PATH=path, CURSOR_SPAWN_CHAIN="x")
        self.assertEqual(p.returncode, 0, p.stderr)
        url = self.opened(log)
        self.assertTrue(url.startswith("cursor://agent-skeleton.editor-browser-open/open?url=file%3A%2F%2F"), url)
        self.assertIn("in%2520page.html", url)  # the space is encoded in the file URL, then again in the query

    def test_open_local_editor_needs_extension(self) -> None:
        path, log = self.fake_openers()
        p = self.run_script(OPEN, str(self.page), PATH=path, CURSOR_SPAWN_CHAIN="x", BROWSER_OPEN_TARGET="editor")
        self.assertEqual(p.returncode, 1)
        p = self.run_script(OPEN, str(self.page), PATH=path, CURSOR_SPAWN_CHAIN="x")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.opened(log), str(self.page))

    def test_open_local_system_target_skips_editor(self) -> None:
        path, log = self.fake_openers()
        (self.tmp / ".vscode" / "extensions" / "agent-skeleton.editor-browser-open-0.1.0").mkdir(parents=True)
        p = self.run_script(OPEN, str(self.page), PATH=path, TERM_PROGRAM="vscode", BROWSER_OPEN_TARGET="system")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.opened(log), str(self.page))


class RichMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="rich-message-")
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def render(self, draft: str) -> tuple[subprocess.CompletedProcess, list | None, str]:
        src = write(self.tmp / "draft.md", draft)
        p = subprocess.run([sys.executable, str(RICH), "--no-open", str(src)], capture_output=True, text=True)
        out = self.tmp / "draft.html"
        if p.returncode or not out.exists():
            return p, None, ""
        page = out.read_text()
        title = re.search(r"const TITLE = (.*?);\n", page).group(1)
        data = re.search(r"const MSGS = (.*?);\n\n", page, re.S).group(1)
        return p, json.loads(data), json.loads(title)

    def test_single_message(self) -> None:
        p, cards, title = self.render(
            "Hi Ana,\n\nDeploy of **api-service** is done, see [PROJ-1](https://x.test/PROJ-1).\n\n"
            "- coverage *82 %*\n  - nested https://x.test/a.\n1. first\n\nbye <b>raw</b> `make test`\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(title, "Messages to send")
        self.assertEqual(len(cards), 1)
        body = cards[0]["msgs"][0]["body"]
        self.assertIn("<b>api-service</b>", body)
        self.assertIn('<a href="https://x.test/PROJ-1">PROJ-1</a>', body)
        self.assertIn("<ul><li>coverage <i>82 %</i><ul><li>nested <a href=\"https://x.test/a\">", body)
        self.assertIn("</ul><ol><li>first</li></ol>", body)
        self.assertIn("&lt;b&gt;raw&lt;/b&gt; make test", body)

    def test_cards_ctx_labels_attach(self) -> None:
        p, cards, title = self.render(
            "# Weekly notes\n=== Ana | ana@example.com | Team A\nctx: module **x**\n--- First\n"
            "attach: 📎 the guide\nHello\n--- Second\nAgain\n=== Luis\nHi Luis\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(title, "Weekly notes")
        self.assertEqual([c["name"] for c in cards], ["Ana", "Luis"])
        ana = cards[0]
        self.assertEqual((ana["email"], ana["group"], ana["ctx"]), ("ana@example.com", "Team A", "module <b>x</b>"))
        self.assertEqual([m["label"] for m in ana["msgs"]], ["First", "Second"])
        self.assertEqual(ana["msgs"][0]["attach"], "📎 the guide")
        self.assertEqual(ana["msgs"][0]["body"], "<p>Hello</p>")

    def test_rejects_em_dash_and_empty(self) -> None:
        p, cards, _ = self.render("one \u2014 two\n")
        self.assertEqual(p.returncode, 2)
        self.assertIn("em dash", p.stderr)
        self.assertFalse((self.tmp / "draft.html").exists())
        p, cards, _ = self.render("=== Nobody\n")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
