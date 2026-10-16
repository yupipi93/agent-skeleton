"""Shared test helpers: load bin/skeleton as a module, build throwaway repo copies."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "skeleton"

_IGNORE = shutil.ignore_patterns(
    ".git", ".claude", ".cursor", ".gemini", ".agents", ".skeleton", "CLAUDE.md", ".mcp.json",
    "local", "projects", "plans", "skeleton.local.toml", "__pycache__", "*.code-workspace", ".DS_Store",
)


def load_cli():
    if "skeleton_cli" in sys.modules:
        return sys.modules["skeleton_cli"]
    loader = importlib.machinery.SourceFileLoader("skeleton_cli", str(CLI))
    spec = importlib.util.spec_from_loader("skeleton_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["skeleton_cli"] = mod
    loader.exec_module(mod)
    return mod


def write(path: Path, text: str, mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    return path


def snapshot(root: Path, with_mtime: bool = True, exclude: tuple[str, ...] = ()) -> dict:
    """Map every path to (kind, payload[, mtime]) without following symlinks."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if rel in exclude or "__pycache__" in rel:
                continue
            if p.is_symlink():
                out[rel] = ("link", os.readlink(p))
            elif p.is_file():
                item = ("file", p.read_bytes())
                out[rel] = item + ((p.stat().st_mtime_ns,) if with_mtime else ())
            else:
                out[rel] = ("dir",)
    return out


class RepoTestCase(unittest.TestCase):
    """Each test gets a fresh copy of the repository and an isolated HOME."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="skeleton-test-")
        self.tmp = Path(self._tmp.name).resolve()
        self.repo = self.tmp / "repo"
        shutil.copytree(ROOT, self.repo, ignore=_IGNORE, symlinks=True)
        (self.repo / "projects").mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def env(self) -> dict:
        env = dict(os.environ)
        env.pop("SKELETON_ROOT", None)
        env.update({"HOME": str(self.home), "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        return env

    def run_cli(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, str(self.repo / "bin" / "skeleton"), *args],
                              cwd=str(self.repo), env=self.env(), capture_output=True, text=True)
        if check and proc.returncode != 0:
            self.fail(f"skeleton {' '.join(args)} exited {proc.returncode}\n"
                      f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        return proc

    def local_toml(self, text: str) -> None:
        write(self.repo / "skeleton.local.toml", text)

    def add_demo_bundle(self) -> Path:
        """A private bundle exercising hooks, MCP, glob and manual rules, a command skill."""
        b = self.repo / "local" / "bundles" / "demo"
        write(b / "bundle.toml", """
            name = "demo"
            title = "Demo"
            emoji = "🧪"
            description = "Test bundle."
            default_enabled = true
            requires = ["core"]
        """)
        write(b / "scripts" / "hook.sh", "#!/bin/sh\nexit 0\n", mode=0o755)
        write(b / "hooks.toml", """
            [[hook]]
            id = "demo-stop"
            event = "stop"
            run = "scripts/hook.sh"
            timeout_s = 20

            [[hook]]
            id = "demo-mcp-guard"
            event = "before_tool"
            run = "scripts/hook.sh"
            timeout_s = 15
            match = { mcp = "atlassian.*" }
            fail_closed = true
            tools = ["claude", "cursor", "gemini"]

            [[hook]]
            id = "demo-shell"
            event = "before_tool"
            run = "scripts/hook.sh"
            match = { shell = true }

            [[hook]]
            id = "demo-prompt"
            event = "prompt_submit"
            run = "scripts/hook.sh"
            args = ["--mode", "context"]
        """)
        write(b / "mcp.toml", """
            [server.local-tool]
            command = "node"
            args = ["${SKELETON_ROOT}/server.js"]
            env = { API_TOKEN = "${DEMO_TOKEN}" }

            [server.remote]
            url = "https://mcp.example.com/mcp"
            headers = { Authorization = "Bearer ${DEMO_TOKEN}" }
        """)
        write(b / "rules" / "tf-only.md", """
            ---
            description: Only for Terraform files.
            apply: glob
            globs: ["**/*.tf", "**/*.tfvars"]
            ---

            # Terraform rule

            Plan before apply.
        """)
        write(b / "rules" / "on-demand.md", """
            ---
            description: Manual rule.
            apply: manual
            ---

            # Manual rule
        """)
        write(b / "skills" / "demo-command" / "SKILL.md", """
            ---
            name: demo-command
            description: "A slash command: does demo things."
            disable-model-invocation: true
            ---

            # Demo command
        """)
        write(b / "skills" / "demo-command" / "references" / "notes.md", "# Notes\n")
        return b
