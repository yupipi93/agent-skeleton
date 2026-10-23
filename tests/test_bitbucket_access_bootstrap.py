"""tools/bitbucket-access-bootstrap without a browser: redaction, specs, stash, Secret Manager.

Secret Manager runs against a fake gcloud that records its argv and stdin, so the
tests prove the token travels on stdin only and never reaches argv or stdout.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tests.helpers import ROOT, write

TOOL = ROOT / "tools" / "bitbucket-access-bootstrap"
BAB = TOOL / "bin" / "bab"
FAKE_VALUE = "ATCTT3xFfGN0" + "x" * 40 + "=ABCD1234"

FAKE_GCLOUD = r'''#!/usr/bin/env python3
import json, os, sys
state = os.environ["FAKE_STATE"]
data = json.load(open(state)) if os.path.exists(state) else {"calls": [], "secrets": {}}
args = sys.argv[1:]
stdin = sys.stdin.read() if "--data-file=-" in args else ""
policy = [a.split("=", 1)[1] for a in args if a.startswith("--replication-policy-file=")]
data["calls"].append({"argv": args, "stdin": stdin,
                      "policy": json.load(open(policy[0])) if policy else None})
def save():
    json.dump(data, open(state, "w"))
pos = [a for a in args if not a.startswith("--")]
if pos[:2] == ["secrets", "describe"]:
    save()
    if pos[2] in data["secrets"]:
        print("projects/123/secrets/" + pos[2]); sys.exit(0)
    sys.stderr.write("ERROR: NOT_FOUND: Secret [x] not found\n"); sys.exit(1)
if pos[:2] == ["secrets", "create"]:
    data["secrets"][pos[2]] = []; save(); sys.exit(0)
if pos[:3] == ["secrets", "versions", "add"]:
    data["secrets"].setdefault(pos[3], []).append(stdin); save()
    print("projects/123/secrets/%s/versions/%d" % (pos[3], len(data["secrets"][pos[3]]))); sys.exit(0)
if pos[:3] == ["secrets", "versions", "access"]:
    name = [a for a in args if a.startswith("--secret=")][0].split("=", 1)[1]
    versions = data["secrets"][name]
    ver = pos[3]
    save()
    sys.stdout.write(versions[-1] if ver == "latest" else versions[int(ver) - 1])
    if os.environ.get("FAKE_CORRUPT"): sys.stdout.write("tampered")
    sys.exit(0)
if pos[:3] == ["kms", "keyrings", "list"]:
    save()
    print("projects/p/locations/europe-west1/keyRings/hub-sql-cmek")
    print("projects/p/locations/europe-west1/keyRings/hub-cmek-europe-west1"); sys.exit(0)
if pos[:3] == ["kms", "keys", "describe"]:
    save()
    ring = [a for a in args if a.startswith("--keyring=")][0].split("=", 1)[1]
    sys.exit(0 if ring == "hub-cmek-europe-west1" and pos[3] == "secrets-cmek" else 1)
save(); sys.exit(3)
'''


def _import():
    sys.path.insert(0, str(TOOL))
    import bab.bitbucket as bitbucket  # noqa: E402
    import bab.redact as redact  # noqa: E402
    return bitbucket, redact


class RedactTest(unittest.TestCase):
    def test_find_and_scrub(self) -> None:
        _, redact = _import()
        text = f"Your token: {FAKE_VALUE} copy it now"
        self.assertEqual(redact.find(text), FAKE_VALUE)
        self.assertNotIn(FAKE_VALUE, redact.scrub(text))
        self.assertIn("ATCTT<redacted>", redact.scrub(text))
        self.assertIsNone(redact.find("ATCTT short"))


class SpecTest(unittest.TestCase):
    def test_urls_per_kind(self) -> None:
        bb, _ = _import()
        self.assertEqual(bb.Target("repository", "acme", repo="web").settings_url,
                         "https://bitbucket.org/acme/web/admin/access-tokens")
        self.assertEqual(bb.Target("project", "acme", project_key="OPS").settings_url,
                         "https://bitbucket.org/acme/workspace/projects/OPS/settings/access-tokens")
        self.assertEqual(bb.Target("workspace", "acme").settings_url,
                         "https://bitbucket.org/acme/workspace/settings/access-tokens")

    def test_validation(self) -> None:
        bb, _ = _import()
        ok = bb.Spec(bb.Target("repository", "acme", repo="web"), "ci-read", ["repository"])
        ok.validate()
        bb.Spec(bb.Target("repository", "acme", repo="web"), "ci-read", ["repository"],
                (date.today() + timedelta(days=365)).isoformat()).validate()
        bad = [
            bb.Spec(bb.Target("repository", "acme"), "n", ["repository"]),
            bb.Spec(bb.Target("project", "acme"), "n", ["repository"]),
            bb.Spec(bb.Target("repository", "acme", repo="web"), "n", ["repo:everything"]),
            bb.Spec(bb.Target("repository", "acme", repo="web"), "n", []),
            bb.Spec(bb.Target("repository", "acme", repo="web"), "n", ["project"]),
            bb.Spec(bb.Target("repository", "acme", repo="web"), "n", ["repository"], "31/12/2027"),
            bb.Spec(bb.Target("repository", "acme", repo="web"), "n", ["repository"], "2020-01-01"),
            bb.Spec(bb.Target("repository", "acme", repo="web"), "n", ["repository"],
                    (date.today() + timedelta(days=366)).isoformat()),
            bb.Spec(bb.Target("repository", "acme/../x", repo="web"), "n", ["repository"]),
        ]
        for spec in bad:
            with self.assertRaises(ValueError, msg=spec):
                spec.validate()


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="bab-")
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "gcloud-state.json"
        self.gcloud = write(self.tmp / "gcloud", FAKE_GCLOUD, mode=0o755)
        self.home = self.tmp / "bab-home"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def env(self, **extra: str) -> dict:
        env = {
            "HOME": str(self.tmp), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "BAB_HOME": str(self.home), "BAB_GCLOUD": str(self.gcloud),
            "BAB_PYTHON": sys.executable, "FAKE_STATE": str(self.state),
        }
        env.update(extra)
        return env

    def bab(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(BAB), *args], capture_output=True, text=True, env=self.env(**extra))

    def seed(self, secrets: dict) -> None:
        self.state.write_text(json.dumps({"calls": [], "secrets": secrets}))

    def stash(self) -> Path:
        stash_dir = self.home / "stash"
        stash_dir.mkdir(parents=True)
        path = stash_dir / "s.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({"value": FAKE_VALUE, "meta": {"gcp_project": "my-project-id",
                                                     "secret_name": "bb-ci", "account": "you@example.com"}}, fh)
        return path

    def calls(self) -> list[dict]:
        return json.loads(self.state.read_text())["calls"]

    def test_create_plan_only_needs_no_browser(self) -> None:
        self.seed({"bb-ci": []})
        p = self.bab("create", "--workspace", "acme", "--repo", "web", "--name", "ci-read",
                     "--scopes", "repository,pullrequest", "--gcp-project", "my-project-id",
                     "--secret-name", "bb-ci", "--account", "you@example.com")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("plan only", p.stdout)
        self.assertIn("projects/my-project-id/secrets/bb-ci (exists", p.stdout)
        self.assertIn("as       NOT CONFIGURED", p.stdout)
        self.assertEqual([c["argv"][:2] for c in self.calls()], [["secrets", "describe"]])
        self.assertIn("--account=you@example.com", self.calls()[0]["argv"])

    def test_expected_account_from_atlassian_env(self) -> None:
        self.seed({"bb-ci": []})
        write(self.tmp / ".config" / "agent-skeleton" / "atlassian.env",
              "BITBUCKET_EMAIL=you@example.com\n", mode=0o600)
        args = ("create", "--workspace", "acme", "--repo", "web", "--name", "n",
                "--scopes", "repository", "--gcp-project", "my-project-id",
                "--secret-name", "bb-ci", "--account", "ops@example.org")
        p = self.bab(*args)
        self.assertIn("as       you@example.com", p.stdout)
        p = self.bab(*args, BAB_EXPECTED_ACCOUNT="bot@example.org")
        self.assertIn("as       bot@example.org", p.stdout)

    def test_yes_without_expected_account_is_refused(self) -> None:
        self.seed({"bb-ci": []})
        p = self.bab("create", "--workspace", "acme", "--repo", "web", "--name", "n",
                     "--scopes", "repository", "--gcp-project", "my-project-id",
                     "--secret-name", "bb-ci", "--account", "you@example.com", "--yes")
        self.assertEqual(p.returncode, 2)
        self.assertIn("no expected Atlassian account", p.stdout)

    def test_create_refuses_missing_secret_without_flag(self) -> None:
        self.seed({})
        p = self.bab("create", "--workspace", "acme", "--repo", "web", "--name", "n",
                     "--scopes", "repository", "--gcp-project", "my-project-id",
                     "--secret-name", "bb-ci", "--account", "you@example.com", "--yes")
        self.assertEqual(p.returncode, 1)
        self.assertIn("does not exist", p.stdout)

    def test_create_bad_scope_is_usage_error(self) -> None:
        p = self.bab("create", "--workspace", "acme", "--repo", "web", "--name", "n",
                     "--scopes", "admin:all", "--gcp-project", "my-project-id",
                     "--secret-name", "bb-ci", "--account", "you@example.com")
        self.assertEqual(p.returncode, 2)

    def test_push_sends_value_on_stdin_only(self) -> None:
        self.seed({"bb-ci": []})
        path = self.stash()
        p = self.bab("push", "--stash", str(path), "--yes")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("versions/1 (read back, matches)", p.stdout)
        self.assertFalse(path.exists())
        self.assertNotIn(FAKE_VALUE, p.stdout + p.stderr)
        for call in self.calls():
            self.assertNotIn(FAKE_VALUE, " ".join(call["argv"]))
        adds = [c for c in self.calls() if c["argv"][:3] == ["secrets", "versions", "add"]]
        self.assertEqual(adds[0]["stdin"], FAKE_VALUE)

    def test_push_creates_secret_in_given_locations(self) -> None:
        self.seed({})
        path = self.stash()
        p = self.bab("push", "--stash", str(path), "--create-secret",
                     "--secret-locations", "europe-west1", "--yes")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        create = [c["argv"] for c in self.calls() if c["argv"][:2] == ["secrets", "create"]][0]
        self.assertIn("--replication-policy=user-managed", create)
        self.assertIn("--locations=europe-west1", create)

    def test_push_creates_cmek_secret_with_auto_key(self) -> None:
        self.seed({})
        path = self.stash()
        p = self.bab("push", "--stash", str(path), "--create-secret", "--secret-locations",
                     "europe-west1", "--kms-key", "auto:*-cmek-europe-west1/secrets-cmek", "--yes")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        create = [c for c in self.calls() if c["argv"][:2] == ["secrets", "create"]][0]
        key = "projects/p/locations/europe-west1/keyRings/hub-cmek-europe-west1/cryptoKeys/secrets-cmek"
        self.assertEqual(create["policy"], {"userManaged": {"replicas": [
            {"location": "europe-west1", "customerManagedEncryption": {"kmsKeyName": key}}]}})
        self.assertEqual(list((self.home).glob("replication-*.json")), [])

    def test_kms_key_per_project(self) -> None:
        self.seed({})
        path = self.stash()
        p = self.bab("push", "--stash", str(path), "--gcp-project", "acme-dev", "--gcp-project",
                     "acme-pro", "--account", "you@example.com", "--create-secret",
                     "--secret-locations", "europe-west1",
                     "--kms-key", "acme-dev=auto:*-cmek-europe-west1/secrets-cmek", "--yes")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        creates = {c["argv"][c["argv"].index("--project=acme-dev") if "--project=acme-dev" in c["argv"]
                   else c["argv"].index("--project=acme-pro")]: c
                   for c in self.calls() if c["argv"][:2] == ["secrets", "create"]}
        self.assertIsNotNone(creates["--project=acme-dev"]["policy"])
        self.assertIsNone(creates["--project=acme-pro"]["policy"])
        self.assertIn("--locations=europe-west1", creates["--project=acme-pro"]["argv"])

    def test_auto_key_missing_stops_before_anything(self) -> None:
        self.seed({})
        path = self.stash()
        p = self.bab("push", "--stash", str(path), "--create-secret", "--secret-locations",
                     "europe-west1", "--kms-key", "auto:*-cmek-europe-west1/other-key", "--yes")
        self.assertEqual(p.returncode, 5)
        self.assertIn("no key 'other-key'", p.stdout)
        self.assertFalse(any(c["argv"][:2] == ["secrets", "create"] for c in self.calls()))

    def test_admin_preset_carries_renovate_scope_and_several_projects(self) -> None:
        self.seed({"web-admin-connector-token": []})
        p = self.bab("create", "--workspace", "acme", "--repo", "web", "--name", "admin-token",
                     "--preset", "admin", "--gcp-project", "acme-dev", "--gcp-project", "acme-pre",
                     "--secret-name", "web-admin-connector-token", "--account", "you@example.com")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("scopes   repository, repository:write, repository:admin, pullrequest, "
                      "pullrequest:write, webhook", p.stdout)
        self.assertIn("projects/acme-dev/secrets/web-admin-connector-token", p.stdout)
        self.assertIn("projects/acme-pre/secrets/web-admin-connector-token", p.stdout)

    def test_push_plan_only_without_yes(self) -> None:
        self.seed({"bb-ci": []})
        path = self.stash()
        p = self.bab("push", "--stash", str(path))
        self.assertEqual(p.returncode, 0)
        self.assertTrue(path.exists())
        self.assertFalse(any(c["argv"][:3] == ["secrets", "versions", "add"] for c in self.calls()))

    def test_push_keeps_stash_when_read_back_differs(self) -> None:
        self.seed({"bb-ci": []})
        path = self.stash()
        p = self.bab("push", "--stash", str(path), "--yes", FAKE_CORRUPT="1")
        self.assertEqual(p.returncode, 5)
        self.assertTrue(path.exists())
        self.assertNotIn(FAKE_VALUE, p.stdout + p.stderr)

    def test_push_refuses_open_stash_mode(self) -> None:
        self.seed({"bb-ci": []})
        path = self.stash()
        path.chmod(0o644)
        p = self.bab("push", "--stash", str(path), "--yes")
        self.assertEqual(p.returncode, 1)
        self.assertIn("expected 0600", p.stdout)

    def test_unmapped_project_needs_an_account(self) -> None:
        self.seed({"bb-ci": []})
        p = self.bab("create", "--workspace", "acme", "--repo", "web", "--name", "n",
                     "--scopes", "repository", "--gcp-project", "my-project-id",
                     "--secret-name", "bb-ci", GCP_ACCOUNT_MAP="other-*=you@example.org")
        self.assertEqual(p.returncode, 1)
        self.assertIn("no gcloud account mapped", p.stdout)

    def test_login_dry_run_uses_tool_profile(self) -> None:
        p = self.bab("login", "--dry-run")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f"--user-data-dir={self.home}/chrome-profile", p.stdout)
        self.assertNotIn("remote-debugging", p.stdout)
        p = self.bab("start", "--dry-run")
        self.assertIn("--remote-debugging-address=127.0.0.1", p.stdout)


if __name__ == "__main__":
    unittest.main()
