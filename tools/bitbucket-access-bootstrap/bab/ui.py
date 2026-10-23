"""Small, forgiving helpers for Bitbucket's React (Atlaskit) UI.

Atlaskit keeps closed modals and hidden copies of controls in the DOM, so "the
first match" is often the wrong one. Every helper here picks by actual
visibility, the lesson gcp-oauth-bootstrap learned on the Cloud Console.
"""

from __future__ import annotations

import re
import time
from typing import Pattern

from . import config

Name = str | Pattern[str]


class NotSignedIn(RuntimeError):
    """Bitbucket sent the browser to the Atlassian sign-in page.

    The tool never types a password: a person signs in with `login` (or finishes
    a step-up prompt in the tool's window) and the command is run again.
    """


def goto(page, url: str, settle_ms: int = 2500) -> None:
    page.goto(url, wait_until="domcontentloaded")
    wait_idle(page, settle_ms)
    if is_login_page(page.url):
        raise NotSignedIn(
            f"Atlassian asks to sign in before {url}: run `bab stop`, then "
            f"`bab login --url '{url}'`, sign in, close the window and run again"
        )


def is_login_page(url: str) -> bool:
    return url.startswith(("https://id.atlassian.com/login", "https://id.atlassian.com/step-up")) or (
        url.startswith(config.BITBUCKET) and "/account/signin" in url
    )


def wait_idle(page, settle_ms: int = 2500) -> None:
    """Wait for spinners to go away, then a fixed settle."""
    deadline = time.monotonic() + 30
    spinner = page.locator("[role=progressbar], [data-testid*=spinner], [aria-busy=true]")
    while time.monotonic() < deadline:
        try:
            if not any(spinner.nth(i).is_visible() for i in range(spinner.count())):
                break
        except Exception:
            break
        time.sleep(0.4)
    page.wait_for_timeout(settle_ms)


def visible(locator, timeout_ms: int = 15000):
    """First genuinely visible match, polling until one shows up."""
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        count = locator.count()
        for i in range(count):
            candidate = locator.nth(i)
            try:
                if candidate.is_visible():
                    return candidate
            except Exception:
                continue
        if time.monotonic() > deadline:
            raise LookupError(f"no visible match among {count} for {locator}")
        time.sleep(0.4)


def present(locator) -> bool:
    try:
        return any(locator.nth(i).is_visible() for i in range(locator.count()))
    except Exception:
        return False


def ci(text: str) -> Pattern[str]:
    """Case-insensitive exact-text pattern."""
    return re.compile(rf"^\s*{re.escape(text)}\s*$", re.I)
