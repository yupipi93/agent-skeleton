"""Where the tool keeps its state (all of it outside the repository) and its settings.

Settings come from the environment first, then ~/.config/agent-skeleton/jsm-portal.env,
then (site only) JIRA_SITE in atlassian.env:

  JPR_SITE               your-org.atlassian.net
  JPR_EXPECTED_ACCOUNT   email or account id the portal session must belong to
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

LINUX = sys.platform.startswith("linux")

TOOL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_DIR.parent.parent
TEXT_GUARD = REPO_ROOT / "kit" / "bundles" / "core" / "scripts" / "text-guard.sh"
ENVFILE_LIB = REPO_ROOT / "kit" / "bundles" / "core" / "scripts" / "lib"

CONFIG_DIR = Path(os.environ.get("SECRETS_CONFIG_DIR", Path.home() / ".config/agent-skeleton"))
CONFIG_FILE = CONFIG_DIR / "jsm-portal.env"
ATLASSIAN_FILE = Path(os.environ.get("ATLASSIAN_ENV_FILE", CONFIG_DIR / "atlassian.env"))

HOME = Path(os.environ.get("JPR_HOME", Path.home() / ".local/share/jsm-portal-requests"))
PROFILE_DIR = HOME / "chrome-profile"
CATALOG_DIR = HOME / "catalog"
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


CHROME_BIN = os.environ.get("JPR_CHROME") or _default_chrome()
# 9339 is gcp-oauth-bootstrap's and 9340 bitbucket-access-bootstrap's.
CDP_PORT = int(os.environ.get("JPR_CDP_PORT", "9341"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
ACTION_TIMEOUT_MS = int(os.environ.get("JPR_ACTION_TIMEOUT_MS", "30000"))


def _file_value(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    sys.path.insert(0, str(ENVFILE_LIB))
    try:
        import envfile  # type: ignore

        return envfile.load(str(path)).get(key, "") or ""
    except Exception:
        return ""
    finally:
        sys.path.pop(0)


def get(key: str, default: str = "") -> str:
    return os.environ.get(key) or _file_value(CONFIG_FILE, key) or default


def site() -> str:
    raw = get("JPR_SITE") or os.environ.get("JIRA_SITE") or _file_value(ATLASSIAN_FILE, "JIRA_SITE")
    raw = raw.removeprefix("https://").removeprefix("http://").split("/")[0]
    if not raw:
        raise SystemExit(
            "jpr: no site configured. Set JPR_SITE=your-org.atlassian.net in the environment "
            f"or in {CONFIG_FILE}"
        )
    return raw


def base_url() -> str:
    return f"https://{site()}"


def expected_account() -> str:
    return get("JPR_EXPECTED_ACCOUNT")


def ensure_dirs() -> None:
    for path in (HOME, PROFILE_DIR, CATALOG_DIR, RUNS_DIR):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
