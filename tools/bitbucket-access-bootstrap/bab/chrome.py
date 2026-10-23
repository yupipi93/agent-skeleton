"""A real Google Chrome on a dedicated profile, attached to over CDP.

Same model as gcp-oauth-bootstrap: the tool never types a password. A human signs
in to Bitbucket once in a plain Chrome window on a profile that belongs only to
this tool, and every later run relaunches that profile with a debugging port bound
to 127.0.0.1 and attaches to it with Playwright.

Two launch modes, never at the same time on the same profile:

- `open_for_login`: plain Chrome, no debugging port, so the Atlassian sign-in (and
  a Google or Microsoft SSO behind it) sees an ordinary browser.
- `start`: the same profile with `--remote-debugging-port`, which Playwright
  attaches to. Chrome only allows that flag on a non-default profile.

The tool stops only the Chrome it launched: the pid is kept in a pidfile and is
checked against the profile path before any signal. No pattern-based kills.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from typing import Iterator

from . import config

BASE_FLAGS = (
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1440,1000",
)
# Linux: login and automated runs must share the cookie encryption key; `basic`
# keeps it in the profile instead of a desktop keyring. Never set on macOS.
LINUX_FLAGS = ("--password-store=basic",)


def cdp_up() -> bool:
    try:
        with urllib.request.urlopen(f"{config.CDP_URL}/json/version", timeout=2) as resp:
            return resp.status == 200
    except OSError:
        return False


def cdp_version() -> dict:
    with urllib.request.urlopen(f"{config.CDP_URL}/json/version", timeout=2) as resp:
        return json.load(resp)


def _command_line(pid: int) -> str:
    return subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()


def own_pid() -> int | None:
    """Pid of the Chrome this tool launched, only while it is still that process."""
    try:
        pid = int(config.PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None
    cmd = _command_line(pid)
    if f"--user-data-dir={config.PROFILE_DIR}" in cmd and "chrom" in cmd.lower():
        return pid
    return None


def launch_plan(extra: list[str], url: str | None) -> list[str]:
    args = [config.CHROME_BIN, f"--user-data-dir={config.PROFILE_DIR}", *BASE_FLAGS]
    if os.environ.get("BAB_PROFILE_DIRECTORY"):
        args.append(f"--profile-directory={os.environ['BAB_PROFILE_DIRECTORY']}")
    if config.LINUX:
        args += LINUX_FLAGS
    args += extra
    if url:
        args.append(url)
    return args


def _launch(extra: list[str], url: str | None, dry_run: bool) -> None:
    args = launch_plan(extra, url)
    if dry_run:
        print(f"argv {args}")
        return
    config.ensure_dirs()
    proc = subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )
    config.PIDFILE.write_text(str(proc.pid))


def open_for_login(url: str, dry_run: bool = False) -> None:
    if (own_pid() or cdp_up()) and not dry_run:
        raise RuntimeError("The tool's Chrome is already running. Run `stop` first.")
    _launch([], url, dry_run)


def start(dry_run: bool = False) -> None:
    """Chrome on the tool profile with the debugging port. Idempotent."""
    if cdp_up() and not dry_run:
        return
    if own_pid() and not dry_run:
        raise RuntimeError(
            "The tool's Chrome is running without the debugging port (login mode). "
            "Close that window or run `stop`, then try again."
        )
    _launch(
        [f"--remote-debugging-port={config.CDP_PORT}", "--remote-debugging-address=127.0.0.1"],
        None,
        dry_run,
    )
    if dry_run:
        return
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if cdp_up():
            return
        time.sleep(0.5)
    raise TimeoutError(f"Chrome did not open its debugging port on {config.CDP_URL}")


def _graceful_close() -> None:
    """Ask Chrome to quit through CDP so it flushes cookies (the session) to disk."""
    if not cdp_up():
        return
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(config.CDP_URL)
            browser.new_browser_cdp_session().send("Browser.close")
    except Exception:
        pass  # fall through to SIGTERM on our own pid


def stop() -> str:
    pid = own_pid()
    was_up = cdp_up()
    _graceful_close()
    deadline = time.monotonic() + 10
    while (cdp_up() or (pid and own_pid())) and time.monotonic() < deadline:
        time.sleep(0.3)
    if pid and own_pid():
        os.kill(pid, signal.SIGTERM)
    config.PIDFILE.unlink(missing_ok=True)
    if pid or was_up:
        return "stopped"
    return "not running"


def _is_app_page(page) -> bool:
    return not page.url.startswith(("devtools://", "chrome-extension://", "chrome://"))


@contextmanager
def attached() -> Iterator:
    """The browser's working tab, for the duration of one command.

    Leaving the block only detaches: the tab and whatever dialog is open stay as
    they were, so the next command (or a person) can see where it stopped.
    """
    from playwright.sync_api import sync_playwright

    start()
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(config.CDP_URL)
        context = browser.contexts[0]
        pages = [p for p in context.pages if _is_app_page(p)]
        page = pages[-1] if pages else context.new_page()
        page.set_default_timeout(config.ACTION_TIMEOUT_MS)
        page.bring_to_front()
        yield page
