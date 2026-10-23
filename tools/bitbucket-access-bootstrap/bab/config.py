"""Where the tool keeps its state, all of it outside the repository.

The browser profile holds a live Atlassian session and a stash file holds a token
until Secret Manager has it, so neither may ever sit in a git working tree.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

LINUX = sys.platform.startswith("linux")

TOOL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_DIR.parent.parent
GCP_ACCOUNT_SCRIPT = REPO_ROOT / "kit" / "bundles" / "gcp" / "scripts" / "gcp-account.py"

HOME = Path(os.environ.get("BAB_HOME", Path.home() / ".local/share/bitbucket-access-bootstrap"))
PROFILE_DIR = HOME / "chrome-profile"
STASH_DIR = HOME / "stash"
RUNS_DIR = HOME / "runs"
PIDFILE = HOME / "chrome.pid"

MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _default_chrome() -> str:
    if not LINUX:
        return MAC_CHROME
    for candidate in ("google-chrome", "google-chrome-stable", "chromium"):
        found = shutil.which(candidate)
        if found:
            return found
    return "/opt/google/chrome/chrome"


CHROME_BIN = os.environ.get("BAB_CHROME") or _default_chrome()
# Not 9339: gcp-oauth-bootstrap uses that one, and both tools may run on one machine.
CDP_PORT = int(os.environ.get("BAB_CDP_PORT", "9340"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
ACTION_TIMEOUT_MS = int(os.environ.get("BAB_ACTION_TIMEOUT_MS", "30000"))

BITBUCKET = "https://bitbucket.org"
BITBUCKET_API = os.environ.get("BAB_BITBUCKET_API", "https://api.bitbucket.org/2.0")


def ensure_dirs() -> None:
    for path in (HOME, PROFILE_DIR, STASH_DIR, RUNS_DIR):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
