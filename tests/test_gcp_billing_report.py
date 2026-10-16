"""tools/billing-exec-report: the shipped synthetic sample renders, reconciles and fails safely."""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests.helpers import ROOT

TOOL = ROOT / "tools" / "billing-exec-report"
GENERATE = TOOL / "generate.py"
SAMPLE = TOOL / "examples" / "sample"
EM_DASH = chr(0x2014)


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


class BillingReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="bexr-test-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(GENERATE), *args], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})

    def test_sample_renders_to_html(self) -> None:
        out = self.tmp / "report.html"
        proc = self.run_tool("--config", str(SAMPLE / "report.toml"), "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("6 pages declared", proc.stdout)
        html = out.read_text(encoding="utf-8")
        self.assertIn("Example platform cloud cost", html)
        self.assertIn("$2,997.30", html)
        self.assertNotIn(EM_DASH, html)
        self.assertEqual(proc.stderr.strip(), "", "sample config should not trigger internal-text warnings")

    def test_json_config_gives_the_same_report(self) -> None:
        cfg = tomllib.loads((SAMPLE / "report.toml").read_text(encoding="utf-8"))
        shutil.copy(SAMPLE / "services.csv", self.tmp / "services.csv")
        (self.tmp / "report.json").write_text(json.dumps(_jsonable(cfg)), encoding="utf-8")
        a, b = self.tmp / "a.html", self.tmp / "b.html"
        self.assertEqual(self.run_tool("--config", str(SAMPLE / "report.toml"), "--out", str(a)).returncode, 0)
        proc = self.run_tool("--config", str(self.tmp / "report.json"), "--out", str(b))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8"))

    def test_figures_that_do_not_reconcile_exit_3(self) -> None:
        csv = (SAMPLE / "services.csv").read_text(encoding="utf-8").replace('"2,997.30"', '"3,100.00"')
        (self.tmp / "services.csv").write_text(csv, encoding="utf-8")
        shutil.copy(SAMPLE / "report.toml", self.tmp / "report.toml")
        proc = self.run_tool("--config", str(self.tmp / "report.toml"), "--out", str(self.tmp / "x.html"))
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("do not reconcile", proc.stderr)

    def test_missing_required_key_exits_2(self) -> None:
        (self.tmp / "bad.json").write_text(json.dumps({"report": {}, "input": {}}), encoding="utf-8")
        proc = self.run_tool("--config", str(self.tmp / "bad.json"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("period_start", proc.stderr)

    def test_pdf_without_chrome_exits_5(self) -> None:
        proc = self.run_tool("--config", str(SAMPLE / "report.toml"), "--out", str(self.tmp / "r.html"),
                             "--pdf", "--chrome", str(self.tmp / "no-such-chrome"))
        self.assertEqual(proc.returncode, 5, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
