"""git bundle: PR helpers (dry runs only), repos-sync guard, skill shape. No network."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

GIT = ROOT / "kit/bundles/git"
SCRIPTS = GIT / "scripts"
SITE = "your-org.atlassian.net"
FAKE_GH = "ghp" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2"

BODY = """## Summary
Add per-key rate limits.

## Changes
- limiter middleware

## Validation
- unit tests

## Rollback
- revert the merge
"""


class GitScriptCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="git-test-")
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.body = self.tmp / "pr.md"
        self.body.write_text(BODY)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, **values):
        cfg = self.home / ".config/agent-skeleton/atlassian.env"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("".join("%s=%s\n" % kv for kv in values.items()))
        cfg.chmod(0o600)

    def run_script(self, name, *args, cwd=None, **env):
        e = {k: v for k, v in os.environ.items()
             if not k.startswith(("JIRA_", "BITBUCKET_", "PR_", "CLAUDECODE", "CURSOR_AGENT", "GEMINI_CLI", "GIT_"))}
        e.update({"HOME": str(self.home)})
        e.update(env)
        return subprocess.run(["/bin/bash", str(SCRIPTS / name), *args], capture_output=True, text=True,
                              env=e, cwd=str(cwd or self.tmp))

    def git(self, *args, cwd):
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                       env=dict(os.environ, HOME=str(self.home), GIT_CONFIG_NOSYSTEM="1"))


class PrGithubTest(GitScriptCase):
    def test_help_and_template(self):
        self.assertEqual(self.run_script("pr-github.sh", "--help").returncode, 0)
        out = self.run_script("pr-github.sh", "--template").stdout
        for section in ("## Summary", "## Changes", "## Validation", "## Rollback"):
            self.assertIn(section, out)

    def test_dry_run_builds_gh_command(self):
        self.config(JIRA_SITE=SITE, PR_DEFAULT_REVIEWERS="alice, bob")
        proc = self.run_script("pr-github.sh", "--title", "feat(api): add limits", "--body-file", str(self.body),
                               "--ticket", "PROJ-123", "--reviewer", "carol", "--reviewer", "alice",
                               "--label", "good first issue", "--draft", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        cmd = proc.stdout.splitlines()[0]
        self.assertIn("gh pr create --title feat\\(api\\):\\ add\\ limits", cmd)
        self.assertIn("--draft", cmd)
        self.assertEqual(cmd.count("--reviewer"), 3)
        self.assertIn("--label good\\ first\\ issue", cmd)
        self.assertIn("Ticket: https://%s/browse/PROJ-123" % SITE, proc.stdout)

    def test_refuses_bad_bodies(self):
        self.assertEqual(self.run_script("pr-github.sh", "--title", "t", "--dry-run").returncode, 2)
        thin = self.tmp / "thin.md"
        thin.write_text("## Summary\nOnly this\n")
        proc = self.run_script("pr-github.sh", "--title", "t", "--body-file", str(thin), "--dry-run")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Changes Validation Rollback", proc.stderr)
        self.assertEqual(self.run_script("pr-github.sh", "--title", "t", "--body-file", str(thin),
                                         "--no-section-check", "--dry-run").returncode, 0)
        leaky = self.tmp / "leaky.md"
        leaky.write_text(BODY + "\ntoken " + FAKE_GH + "\n")
        proc = self.run_script("pr-github.sh", "--title", "t", "--body-file", str(leaky), "--dry-run")
        self.assertEqual(proc.returncode, 5)
        self.assertNotIn(FAKE_GH, proc.stdout + proc.stderr)

    def test_ticket_without_site_is_plain_key(self):
        proc = self.run_script("pr-github.sh", "--title", "t", "--body-file", str(self.body),
                               "--ticket", "PROJ-9", "--dry-run")
        self.assertIn("Ticket: PROJ-9", proc.stdout)


class PrBitbucketTest(GitScriptCase):
    def make_repo(self):
        repo = self.tmp / "widgets"
        repo.mkdir()
        self.git("init", "-q", "-b", "feat/limits", cwd=repo)
        ssh_remote = "git" + "@" + "bitbucket.org:acme/widgets.git"  # split for the denylist
        self.git("remote", "add", "origin", ssh_remote, cwd=repo)
        return repo

    def test_dry_run_payload_from_remote(self):
        repo = self.make_repo()
        self.config(PR_DEFAULT_REVIEWERS="557058:abc,{1111-2222}", JIRA_SITE=SITE)
        proc = self.run_script("pr-bitbucket.sh", "-C", str(repo), "--title", "fix(dns): ttl",
                               "--body-file", str(self.body), "--ticket", "PROJ-5", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        first, rest = proc.stdout.split("\n", 1)
        self.assertEqual(first, "dry-run: POST https://api.bitbucket.org/2.0/repositories/acme/widgets/pullrequests")
        payload = json.loads(rest)
        self.assertEqual(payload["source"]["branch"]["name"], "feat/limits")
        self.assertEqual(payload["destination"]["branch"]["name"], "main")
        self.assertTrue(payload["close_source_branch"])
        self.assertEqual(payload["reviewers"], [{"account_id": "557058:abc"}, {"uuid": "{1111-2222}"}])
        self.assertIn("https://%s/browse/PROJ-5" % SITE, payload["description"])

    def test_missing_credentials_and_repo(self):
        repo = self.make_repo()
        proc = self.run_script("pr-bitbucket.sh", "-C", str(repo), "--title", "t", "--body-file", str(self.body))
        self.assertEqual(proc.returncode, 3)
        self.assertIn("BITBUCKET_API_TOKEN", proc.stderr)
        plain = self.tmp / "plain"
        plain.mkdir()
        proc = self.run_script("pr-bitbucket.sh", "-C", str(plain), "--title", "t", "--body-file", str(self.body),
                               "--workspace", "acme", "--dry-run")
        self.assertEqual(proc.returncode, 2)


class ReposSyncTest(GitScriptCase):
    def test_dry_run_lists_and_agent_guard(self):
        projects = self.tmp / "projects"
        for name in ("one", "two"):
            (projects / name).mkdir(parents=True)
            self.git("init", "-q", cwd=projects / name)
        (projects / "one" / ".terraform" / "modules" / "m").mkdir(parents=True)
        self.git("init", "-q", cwd=projects / "one" / ".terraform" / "modules" / "m")
        proc = self.run_script("repos-sync.sh", "--projects-dir", str(projects), "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("would sync:"), 2)
        proc = self.run_script("repos-sync.sh", "--projects-dir", str(projects), CLAUDECODE="1")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("--i-am-human", proc.stdout)
        self.assertEqual(self.run_script("repos-sync.sh", "--jobs", "x").returncode, 2)
        self.assertEqual(self.run_script("repos-sync.sh", "--help").returncode, 0)


class GitBundleShapeTest(unittest.TestCase):
    def test_skills_rules_and_command(self):
        names = sorted(p.name for p in (GIT / "skills").iterdir() if (p / "SKILL.md").exists())
        self.assertEqual(names, ["git-branch-pr-workflow", "git-conventional-commits", "git-pr-bitbucket",
                                 "git-pr-github", "git-worktrees", "worktree"])
        self.assertIn("disable-model-invocation: true", (GIT / "skills/worktree/SKILL.md").read_text())
        self.assertTrue((GIT / "rules/worktree-for-project-writes.md").exists())
        for p in SCRIPTS.glob("*.sh"):
            self.assertTrue(os.access(p, os.X_OK), p)


if __name__ == "__main__":
    unittest.main()
