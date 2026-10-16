#!/usr/bin/env python3
"""Build an executive cloud-cost report from a Google Cloud Billing export.

    python3 generate.py --config reports/<name>/report.toml --pdf

The config may be TOML (stdlib on Python 3.11+), JSON (any Python), or YAML
(only when PyYAML happens to be installed; it is never required).

Reads the billing export plus a report config, computes one canonical set of
figures, and writes a self-contained print-ready HTML file. With --pdf it also
renders the PDF through headless Chrome and verifies that the PDF has exactly as
many pages as the document declares, so a layout overflow fails the build instead
of shipping a document whose own footer lies about its pagination.

Exit codes: 0 ok, 2 bad usage or config, 3 reconciliation failure,
4 pagination mismatch, 5 PDF conversion failure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bexr import charts, metrics, parse, render  # noqa: E402

CHROME_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium",
                     "chromium-browser", "chrome")
# macOS installs browsers as app bundles, never on PATH, so look for them there.
CHROME_APP_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "~/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/snap/bin/chromium",
)
TOLERANCE = 0.02


def load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    try:
        if suffix == ".toml":
            try:
                import tomllib
            except ModuleNotFoundError:
                sys.exit("error: TOML configs need Python 3.11+; use JSON instead")
            cfg = tomllib.loads(text)
        elif suffix in {".yaml", ".yml"}:
            try:
                import yaml
            except ModuleNotFoundError:
                sys.exit("error: YAML configs need PyYAML, which is optional; "
                         "use TOML or JSON instead")
            cfg = yaml.safe_load(text)
        else:
            cfg = json.loads(text)
    except ValueError as e:  # tomllib.TOMLDecodeError and JSONDecodeError
        sys.exit(f"error: cannot parse {path}: {e}")
    if not isinstance(cfg, dict):
        sys.exit(f"error: {path} did not parse into a mapping")
    for key in ("report", "input"):
        if key not in cfg:
            sys.exit(f"error: {path} is missing the required '{key}' section")
    for key in ("period_start", "period_end"):
        if key not in cfg["report"]:
            sys.exit(f"error: report.{key} is required")
    if "services_csv" not in cfg["input"]:
        sys.exit("error: input.services_csv is required")
    return cfg


def resolve(base: Path, value: str) -> Path:
    p = Path(str(value)).expanduser()
    return p if p.is_absolute() else (base / p)


def reconcile(m: metrics.Model, export: parse.ServicesExport) -> list[str]:
    """Cross-check the model against the export. Any gap is a hard error."""
    problems = []
    rows_sum = sum(s.subtotal for s in m.services)
    if abs(rows_sum - m.subtotal) > max(TOLERANCE, m.subtotal * 0.002):
        problems.append(
            f"service rows sum to {rows_sum:.2f} but the subtotal is "
            f"{m.subtotal:.2f}")
    if abs(m.focus.subtotal + m.rest.subtotal - m.subtotal) > TOLERANCE:
        problems.append("focus plus rest does not equal the subtotal")
    if abs(m.always_on.subtotal + m.usage_driven.subtotal - m.subtotal) > TOLERANCE:
        problems.append("always-on plus usage-driven does not equal the subtotal")
    net = m.list_total + m.savings_total
    if abs(net - m.subtotal) > max(0.05, m.subtotal * 0.005):
        problems.append(
            f"list {m.list_total:.2f} plus savings {m.savings_total:.2f} gives "
            f"{net:.2f}, not the subtotal {m.subtotal:.2f}")
    if export.reported_total is not None and \
            abs(export.reported_total - m.subtotal) > TOLERANCE:
        problems.append(
            f"the export reports a filtered total of {export.reported_total:.2f} "
            f"but the subtotal used is {m.subtotal:.2f}")
    if m.daily:
        gap = abs(m.daily.total - m.subtotal)
        if gap > max(0.05, m.subtotal * 0.005):
            problems.append(
                f"the daily series sums to {m.daily.total:.2f}, which is "
                f"{gap:.2f} away from the subtotal")
    for s in m.services:
        if s.subtotal < 0:
            problems.append(f"{s.name} has a negative subtotal")
    return problems


def find_chrome(explicit: str | None) -> str | None:
    """--chrome, then $CHROME_BIN, then PATH, then the usual app-bundle paths."""
    explicit = explicit or os.environ.get("CHROME_BIN") or None
    if explicit:
        explicit = str(Path(explicit).expanduser()) if "/" in explicit else explicit
        return explicit if shutil.which(explicit) or Path(explicit).exists() else None
    for c in CHROME_CANDIDATES:
        if shutil.which(c):
            return c
    for app in CHROME_APP_PATHS:
        path = Path(app).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def pdf_page_count(path: Path) -> int | None:
    """Count pages without a PDF library.

    Prefers the page-tree /Count, falls back to counting /Type /Page objects.
    Returns None when neither is readable, which is reported rather than assumed.
    """
    data = path.read_bytes()
    counts = [int(m.group(1)) for m in
              re.finditer(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data, re.S)]
    counts += [int(m.group(1)) for m in
               re.finditer(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", data, re.S)]
    if counts:
        return max(counts)
    pages = len(re.findall(rb"/Type\s*/Page(?![sA-Za-z])", data))
    return pages or None


def to_pdf(chrome: str, html: Path, pdf: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="bexr-chrome-") as profile:
        cmd = [
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
            f"--user-data-dir={profile}", "--no-first-run",
            "--no-pdf-header-footer", "--disable-extensions",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=6000",
            f"--print-to-pdf={pdf}", html.resolve().as_uri(),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not pdf.exists() or pdf.stat().st_size == 0:
        sys.stderr.write(res.stderr[-2000:] + "\n")
        sys.exit(5)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Executive cloud-cost report generator")
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", type=Path,
                    help="HTML output path (default: alongside the config)")
    ap.add_argument("--pdf", nargs="?", const=True, default=False,
                    help="also render a PDF, optionally to this path")
    ap.add_argument("--chrome", help="browser binary to use for the PDF")
    ap.add_argument("--allow-pagination-drift", action="store_true",
                    help="warn instead of failing when the PDF page count "
                         "differs from the declared one")
    args = ap.parse_args()

    cfg_path = args.config.expanduser().resolve()
    if not cfg_path.exists():
        sys.exit(f"error: no such config: {cfg_path}")
    cfg = load_config(cfg_path)
    base = cfg_path.parent

    services_csv = resolve(base, cfg["input"]["services_csv"])
    if not services_csv.exists():
        sys.exit(f"error: no such services export: {services_csv}")
    try:
        export = parse.read_services_csv(services_csv)
    except parse.ParseError as e:
        sys.exit(f"error: {e}")

    daily = None
    if cfg["input"].get("daily_csv"):
        p = resolve(base, cfg["input"]["daily_csv"])
        if not p.exists():
            sys.exit(f"error: no such daily export: {p}")
        daily = parse.read_daily_csv(p)
    elif cfg.get("daily"):
        daily = parse.daily_from_config(cfg["daily"])

    try:
        model = metrics.build(export, cfg, daily)
    except (ValueError, KeyError) as e:
        sys.exit(f"error: {e}")

    problems = reconcile(model, export)
    if problems:
        print("error: the figures do not reconcile with the export:",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 3

    html, declared_pages = render.render(model)
    if render.EM_DASH in html:
        print("error: an em dash survived into the output", file=sys.stderr)
        return 3

    out = (args.out or (base / f"{cfg_path.stem}.html")).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"html  {out}  ({declared_pages} pages declared, "
          f"{len(html) / 1024:.0f} KB, self-contained)")

    rc = 0
    if args.pdf:
        pdf = Path(args.pdf) if isinstance(args.pdf, str) else \
            out.with_suffix(".pdf")
        pdf = pdf.expanduser()
        pdf.parent.mkdir(parents=True, exist_ok=True)
        chrome = find_chrome(args.chrome)
        if not chrome:
            print("error: no Chrome or Chromium found for PDF conversion; "
                  "pass --chrome", file=sys.stderr)
            return 5
        to_pdf(chrome, out, pdf)
        actual = pdf_page_count(pdf)
        size = pdf.stat().st_size / 1024
        if actual is None:
            print(f"pdf   {pdf}  ({size:.0f} KB, page count unreadable)")
        elif actual != declared_pages:
            msg = (f"pagination mismatch: the document declares "
                   f"{declared_pages} pages, the PDF has {actual}. A section is "
                   f"overflowing its page.")
            if args.allow_pagination_drift:
                print(f"warning: {msg}", file=sys.stderr)
                print(f"pdf   {pdf}  ({size:.0f} KB, {actual} pages)")
            else:
                print(f"error: {msg}", file=sys.stderr)
                print(f"pdf   {pdf}  ({size:.0f} KB, {actual} pages)")
                rc = 4
        else:
            print(f"pdf   {pdf}  ({size:.0f} KB, {actual} pages, pagination ok)")

    _ = charts  # imported for its side-effect-free availability to templates
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
