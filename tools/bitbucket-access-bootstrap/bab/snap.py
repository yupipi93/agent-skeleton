"""Capture where the browser is: URL, screenshot, accessibility tree.

Bitbucket changes its markup without notice, so no step trusts a selector
blindly. A snapshot is what a person or an agent reads to see which screen a run
stopped on. A token on screen is redacted from the text and the screenshot is
skipped, because pixels cannot be redacted.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import config, redact


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "snap"


def input_values(page) -> list[str]:
    """A token often sits in a read-only input, which the aria tree may not show."""
    try:
        return page.eval_on_selector_all("input, textarea", "els => els.map(e => e.value || '')")
    except Exception:
        return []


def take(page, label: str = "snap") -> Path:
    config.ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = config.RUNS_DIR / f"{stamp}-{_slug(label)}"
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)

    try:
        tree = page.locator("body").aria_snapshot(timeout=10000)
    except Exception as exc:  # a half-rendered page can refuse; the URL still helps
        tree = f"(aria snapshot failed: {exc})"
    if redact.contains(tree) or any(redact.contains(v) for v in input_values(page)):
        (out / "screenshot-skipped.txt").write_text("a token was on screen\n")
    else:
        page.screenshot(path=str(out / "screenshot.png"), full_page=False)
    (out / "aria.yaml").write_text(redact.scrub(tree))
    (out / "url.txt").write_text(f"{page.url}\n{redact.scrub(page.title())}\n")
    return out


def summary(page, out: Path, max_lines: int = 80) -> str:
    """A short text view for the terminal: URL, headings, dialog, controls."""
    tree = (out / "aria.yaml").read_text().splitlines()
    wanted = re.compile(r"- (heading|dialog|button|textbox|combobox|radio|checkbox|alert|link|group|row)")
    picked = [line for line in tree if wanted.search(line)][:max_lines]
    return "\n".join(
        [f"url:   {page.url}", f"title: {redact.scrub(page.title())}", f"files: {out}", "---", *picked]
    )
