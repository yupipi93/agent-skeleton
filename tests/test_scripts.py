"""Shell and Python scripts of the kit: syntax, text guard, envfile, re-exec."""
import fnmatch
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

GUARD = ROOT / "kit/bundles/core/scripts/text-guard.sh"
ENVFILE = ROOT / "kit/bundles/core/scripts/lib/envfile.py"
LIB = ROOT / "kit/bundles/core/scripts/lib"

# Fake secrets assembled at runtime so the repository never contains one.
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
FAKE_GH = "ghp" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2"


# Pruned at any depth; os.walk never follows a symlink (projects/ holds links to whole repos).
SKIP_DIRS = {".git", ".claude", ".cursor", ".gemini", ".agents", ".skeleton", "local", "projects",
             "node_modules", ".terraform", "__pycache__"}


def tracked(pattern):
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if fnmatch.fnmatch(fn, pattern) and not p.is_symlink():
                found.append(p)
    return iter(sorted(found))


class SyntaxTest(unittest.TestCase):
    def test_shell_scripts_parse_with_bin_bash(self):
        bash = "/bin/bash" if os.path.exists("/bin/bash") else shutil.which("bash")
        for p in list(tracked("*.sh")):
            proc = subprocess.run([bash, "-n", str(p)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"{p}: {proc.stderr}")

    def test_python_compiles(self):
        files = list(tracked("*.py")) + [ROOT / "bin" / "skeleton"]
        for p in files:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")

    def test_scripts_executable(self):
        for p in [ROOT / "bin/skeleton", ROOT / "bin/install-mac.sh", GUARD]:
            self.assertTrue(os.access(p, os.X_OK), p)

    @unittest.skipUnless(os.path.exists("/usr/bin/python3"), "no system python3")
    def test_reexec_from_old_python(self):
        env = dict(os.environ, PATH=f"{Path(sys.executable).parent}:/usr/bin:/bin", NO_COLOR="1")
        env.pop("SKELETON_REEXEC", None)
        proc = subprocess.run(["/usr/bin/python3", str(ROOT / "bin/skeleton"), "--help"],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("usage: skeleton", proc.stdout)


class TextGuardTest(unittest.TestCase):
    def guard(self, text, *args):
        return subprocess.run(["/bin/bash", str(GUARD), *args], input=text, capture_output=True, text=True)

    def test_clean_text_passes(self):
        self.assertEqual(self.guard("Deployed the fix, see the dashboard.\n").returncode, 0)

    def test_secrets_blocked_without_echo(self):
        for secret, label in ((FAKE_AWS, "aws-access-key"), (FAKE_GH, "github-token"),
                              ("password=" + "hunter2hunter2", "credential-assignment")):
            proc = self.guard(f"Here it is: {secret}\n")
            self.assertEqual(proc.returncode, 2, secret)
            self.assertIn(label, proc.stderr)
            self.assertNotIn(secret, proc.stderr + proc.stdout)

    def test_client_json(self):
        self.assertEqual(self.guard('{"tool_input": {"x": 1}}', "--client", "cursor").stdout.strip(),
                         '{"permission":"allow"}')
        denied = self.guard('{"body": "' + FAKE_AWS + '"}', "--client", "cursor")
        self.assertEqual(denied.returncode, 2)
        self.assertIn('"permission":"deny"', denied.stdout)
        self.assertEqual(self.guard("ok", "--client", "claude").stdout, "")

    def test_em_dash_optional(self):
        text = "one \u2014 two\n"
        self.assertEqual(self.guard(text).returncode, 0)
        self.assertEqual(self.guard(text, "--em-dash").returncode, 2)

    def test_file_mode_and_fail_closed(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(FAKE_AWS)
        try:
            self.assertEqual(subprocess.run(["/bin/bash", str(GUARD), "--file", f.name],
                                            capture_output=True).returncode, 2)
        finally:
            os.unlink(f.name)
        proc = self.guard("x", "--patterns", "/nonexistent/patterns.txt")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(self.guard("x", "--bogus").returncode, 64)

    def test_python_scanner_agrees(self):
        sys.path.insert(0, str(LIB))
        try:
            import secretscan
        finally:
            sys.path.pop(0)
        for text in (FAKE_AWS, FAKE_GH, "token: abcdefghijk", "all good here"):
            shell_blocked = self.guard(text).returncode == 2
            self.assertEqual(secretscan.scan(text) is not None, shell_blocked, text)


class EnvfileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "cfg"
        self.file = self.dir / "demo.env"

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args, stdin=None, env=None):
        e = dict(os.environ)
        e.pop("DEMO_TOKEN", None)
        e.update(env or {})
        return subprocess.run([sys.executable, str(ENVFILE), *args], input=stdin, capture_output=True,
                              text=True, env=e)

    def test_set_from_stdin_get_and_modes(self):
        self.assertEqual(self.cli("set", str(self.file), "DEMO_TOKEN", stdin="s3cr3t value\n").returncode, 0)
        self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode), 0o700)
        self.assertEqual(self.cli("get", str(self.file), "DEMO_TOKEN").stdout, "s3cr3t value\n")
        self.assertEqual(self.cli("get", str(self.file), "DEMO_TOKEN", env={"DEMO_TOKEN": "env"}).stdout, "env\n")
        self.assertEqual(self.cli("get", str(self.file), "DEMO_TOKEN", "--no-env",
                                  env={"DEMO_TOKEN": "env"}).stdout, "s3cr3t value\n")
        self.assertEqual(self.cli("get", str(self.file), "MISSING").returncode, 1)
        self.assertEqual(self.cli("get", str(self.file), "MISSING", "--default", "d").stdout, "d\n")
        self.assertEqual(self.cli("keys", str(self.file)).stdout, "DEMO_TOKEN\n")
        self.assertEqual(self.cli("check-mode", str(self.file)).returncode, 0)
        self.file.chmod(0o644)
        self.assertEqual(self.cli("check-mode", str(self.file)).returncode, 1)
        self.assertEqual(self.cli("check-mode", str(self.dir / "nope")).returncode, 2)

    def test_preserves_comments_and_parses_quotes(self):
        self.dir.mkdir(mode=0o700)
        self.file.write_text("# comment\nexport A='x y'\nB=\"q \\\"z\\\"\"\nC=plain # note\n")
        self.cli("set", str(self.file), "C", "--value", "new")
        text = self.file.read_text()
        self.assertTrue(text.startswith("# comment\nexport A='x y'\n"))
        self.assertEqual(self.cli("get", str(self.file), "A").stdout, "x y\n")
        self.assertEqual(self.cli("get", str(self.file), "B").stdout, 'q "z"\n')
        self.assertEqual(self.cli("get", str(self.file), "C").stdout, "new\n")
        self.assertEqual(self.cli("unset", str(self.file), "A").returncode, 0)
        self.assertNotIn("A=", self.file.read_text())


class SecretsShTest(unittest.TestCase):
    def test_curl_helpers_keep_secrets_off_argv(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "curl"
            fake.write_text('#!/bin/sh\necho "ARGS: $*"\necho "STDIN:"\ncat\n')
            fake.chmod(0o755)
            token = "tok" + "en-value-123"
            script = (f'. "{LIB}/secrets.sh"; '
                      f'secrets_curl_bearer "{token}" -s https://api.example.com/x; '
                      f'secrets_curl_basic "you@example.com" "{token}" https://api.example.com/y')
            env = dict(os.environ, PATH=f"{d}:{os.environ['PATH']}")
            out = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, env=env).stdout
        for line in out.splitlines():
            if line.startswith("ARGS:"):
                self.assertNotIn(token, line)
                self.assertIn("-K -", line)
        self.assertIn(f'header = "Authorization: Bearer {token}"', out)
        self.assertIn(f'user = "you@example.com:{token}"', out)


class InstallMacTest(unittest.TestCase):
    def test_dry_run_changes_nothing(self):
        proc = subprocess.run(["/bin/bash", str(ROOT / "bin/install-mac.sh"), "--dry-run", "--skip-brew"],
                              capture_output=True, text=True, env=dict(os.environ, NO_COLOR="1"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[dry-run]", proc.stdout)

    def test_brewfile_groups(self):
        script = (
            f'BREWFILE="{ROOT}/Brewfile"; '
            + "eval \"$(sed -n '/^brewfile_groups()/,/^}/p' " + f'"{ROOT}/bin/install-mac.sh")"; '
            + "brewfile_groups core,terraform"
        )
        out = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True).stdout
        self.assertIn('brew "git"', out)
        self.assertIn('tap "hashicorp/tap"', out)
        self.assertNotIn("ffmpeg", out)
        self.assertNotIn("google-cloud-sdk", out)


if __name__ == "__main__":
    unittest.main()
