"""Capture where the browser is: URL, accessibility tree and (optionally) a screenshot.

Portal markup changes without notice, so a snapshot is what a person or an agent
reads to see which screen a run stopped on.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import config


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "snap"


def take(page, label: str = "snap", screenshot: bool = True) -> Path:
    config.ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = config.RUNS_DIR / f"{stamp}-{_slug(label)}"
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    try:
        tree = page.locator("body").aria_snapshot(timeout=10000)
    except Exception as exc:  # a half-rendered page can refuse; the URL still helps
        tree = f"(aria snapshot failed: {exc})"
    if screenshot:
        page.screenshot(path=str(out / "screenshot.png"), full_page=True)
    (out / "aria.yaml").write_text(tree)
    (out / "url.txt").write_text(f"{page.url}\n{page.title()}\n")
    return out


def summary(page, out: Path, max_lines: int = 80) -> str:
    """A short text view for the terminal: URL, headings, controls."""
    tree = (out / "aria.yaml").read_text().splitlines()
    wanted = re.compile(r"- (heading|dialog|button|textbox|combobox|radio|checkbox|alert|link|group)")
    picked = [line for line in tree if wanted.search(line)][:max_lines]
    return "\n".join([f"url:   {page.url}", f"title: {page.title()}", f"files: {out}", "---", *picked])
