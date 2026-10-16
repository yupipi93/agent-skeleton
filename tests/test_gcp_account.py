"""kit/bundles/gcp/scripts/gcp-account.py resolves accounts from GCP_ACCOUNT_MAP, read-only."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

SCRIPT = ROOT / "kit" / "bundles" / "gcp" / "scripts" / "gcp-account.py"
MAP = "acme-client-*=you@example.org acme-*=work@example.com,*=you@example.com"


class GcpAccountTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="gcp-account-")
        self.home = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_script(self, *args: str, mapping: str | None = MAP) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        if mapping is not None:
            env["GCP_ACCOUNT_MAP"] = mapping
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def test_first_match_wins(self) -> None:
        self.assertEqual(self.run_script("acme-client-dev").stdout.strip(), "you@example.org")
        self.assertEqual(self.run_script("acme-dev").stdout.strip(), "work@example.com")
        self.assertEqual(self.run_script("my-project-id").stdout.strip(), "you@example.com")

    def test_no_match_exits_1(self) -> None:
        p = self.run_script("my-project-id", mapping="acme-*=work@example.com")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout, "")

    def test_no_map_exits_1(self) -> None:
        p = self.run_script("my-project-id", mapping=None)
        self.assertEqual(p.returncode, 1)
        self.assertIn("GCP_ACCOUNT_MAP", p.stderr)

    def test_reads_config_file(self) -> None:
        cfg = self.home / ".config" / "agent-skeleton" / "gcp.env"
        cfg.parent.mkdir(parents=True)
        cfg.write_text('GCP_ACCOUNT_MAP="team-*=you@example.com"\n', encoding="utf-8")
        cfg.chmod(0o644)
        p = self.run_script("team-dev", mapping=None)
        self.assertEqual(p.stdout.strip(), "you@example.com")
        self.assertIn("chmod 600", p.stderr)

    def test_list(self) -> None:
        p = self.run_script("--list")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(len(p.stdout.strip().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
