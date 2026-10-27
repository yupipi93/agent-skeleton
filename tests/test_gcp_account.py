"""kit/bundles/gcp/scripts/gcp-account.py resolves accounts from GCP_ACCOUNT_MAP, then learns unmatched ids."""
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
TWO = "acme-*=work@example.com other-*=you@example.org"

# Fake gcloud: FAKE_VISIBLE="account:project ..." says who sees what; every call is logged.
FAKE_GCLOUD = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
acct=""; for a in "$@"; do case "$a" in --account=*) acct="${a#--account=}";; esac; done
if [ "$1 $2" = "projects describe" ]; then
  for pair in $FAKE_VISIBLE; do [ "$pair" = "$acct:$3" ] && { echo "$3"; exit 0; }; done
  echo "ERROR: not found" >&2; exit 1
fi
if [ "$1 $2" = "projects list" ]; then
  for pair in $FAKE_VISIBLE; do [ "${pair%%:*}" = "$acct" ] && echo "${pair#*:}"; done
  exit 0
fi
if [ "$1 $2" = "organizations list" ]; then
  for pair in $FAKE_ORGS; do [ "${pair%%:*}" = "$acct" ] && echo "organizations/${pair#*:}"; done
  exit 0
fi
if [ "$1 $2" = "projects get-ancestors" ]; then
  echo "$3 project"
  for pair in $FAKE_PARENT; do [ "${pair%%:*}" = "$3" ] && echo "${pair#*:} organization"; done
  exit 0
fi
exit 2
"""
ORGS = "work@example.com:111 you@example.org:222"


class GcpAccountTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="gcp-account-")
        self.home = Path(self._tmp.name)
        bindir = self.home / "bin"
        bindir.mkdir()
        fake = bindir / "gcloud"
        fake.write_text(FAKE_GCLOUD, encoding="utf-8")
        fake.chmod(0o755)
        self.log = self.home / "gcloud.log"
        self.learned = self.home / ".config" / "agent-skeleton" / "gcp-account-learned.txt"
        self.path = "%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_script(self, *args: str, mapping: str | None = MAP, visible: str = "",
                   **extra: str) -> subprocess.CompletedProcess:
        env = {"HOME": str(self.home), "PATH": self.path, "FAKE_LOG": str(self.log), "FAKE_VISIBLE": visible,
               "FAKE_ORGS": ORGS}
        if mapping is not None:
            env["GCP_ACCOUNT_MAP"] = mapping
        env.update(extra)
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)

    def gcloud_calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_first_match_wins(self) -> None:
        self.assertEqual(self.run_script("acme-client-dev").stdout.strip(), "you@example.org")
        self.assertEqual(self.run_script("acme-dev").stdout.strip(), "work@example.com")
        self.assertEqual(self.run_script("my-project-id").stdout.strip(), "you@example.com")
        self.assertEqual(self.gcloud_calls(), [])

    def test_no_match_exits_1(self) -> None:
        p = self.run_script("my-project-id", mapping="acme-*=work@example.com")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(p.stdout, "")
        self.assertFalse(self.learned.exists())

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

    def test_discovers_and_learns_unmatched_project(self) -> None:
        p = self.run_script("brand--core--pro", "--explain", mapping=TWO,
                            visible="you@example.org:brand--core--pro")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "you@example.org")
        self.assertIn("discovered", p.stderr)
        self.assertIn("brand--core--pro=you@example.org", self.learned.read_text())
        self.assertEqual(self.learned.stat().st_mode & 0o777, 0o600)
        # Second call comes from the learned file, with no gcloud call.
        self.log.unlink()
        p = self.run_script("brand--core--pro", "--explain", mapping=TWO)
        self.assertEqual(p.stdout.strip(), "you@example.org")
        self.assertIn("learned", p.stderr)
        self.assertEqual(self.gcloud_calls(), [])
        self.assertIn("(learned)", self.run_script("--list", mapping=TWO).stdout)

    def test_shared_project_goes_to_its_home_org_account(self) -> None:
        both = "work@example.com:shared-x you@example.org:shared-x"
        p = self.run_script("shared-x", mapping=TWO, visible=both, FAKE_PARENT="shared-x:222")
        self.assertEqual(p.stdout.strip(), "you@example.org")
        self.assertEqual(p.stderr, "")
        self.learned.unlink()
        p = self.run_script("shared-x", mapping=TWO, visible=both, FAKE_PARENT="shared-x:999")
        self.assertEqual(p.stdout.strip(), "work@example.com")
        self.assertIn("none of theirs", p.stderr)

    def test_discovery_can_be_disabled(self) -> None:
        for extra_args, env in ((("--no-discover",), {}), ((), {"GCP_ACCOUNT_DISCOVER": "0"})):
            p = self.run_script("brand-x", *extra_args, mapping=TWO, visible="you@example.org:brand-x", **env)
            self.assertEqual(p.returncode, 1)
        self.assertEqual(self.gcloud_calls(), [])

    def test_sync_learns_only_unmatched_projects(self) -> None:
        self.learned.parent.mkdir(parents=True)
        self.learned.write_text("brand-c=work@example.com\n")  # a wrong earlier guess
        visible = ("work@example.com:acme-dev work@example.com:brand-a you@example.org:brand-b "
                   "work@example.com:brand-c you@example.org:brand-c")
        p = self.run_script("--sync", mapping=TWO, visible=visible, FAKE_PARENT="brand-c:222")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("learned or corrected 3", p.stdout)
        text = self.learned.read_text()
        self.assertIn("brand-a=work@example.com", text)
        self.assertIn("brand-b=you@example.org", text)
        self.assertIn("brand-c=you@example.org", text)
        self.assertNotIn("acme-dev", text)


if __name__ == "__main__":
    unittest.main()
