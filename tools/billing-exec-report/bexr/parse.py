"""Parse Google Cloud Billing CSV exports.

The console lets you export a "Reports" view grouped by service. That export is
the primary input of this tool. Column names vary with the currency and with the
credits you have enabled, so every column is located by name, never by position.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
from dataclasses import dataclass, field


CURRENCY_RE = re.compile(r"\(([^)]+)\)\s*$")

# Header prefixes we know how to read. Order matters only for reporting.
COLS = {
    "service": ("service description", "service"),
    "service_id": ("service id",),
    "list_cost": ("list cost", "cost before"),
    "negotiated": ("negotiated savings",),
    "programmes": ("savings programmes", "savings programs"),
    "other_savings": ("other savings", "promotions and others", "credits"),
    "unrounded": ("unrounded subtotal",),
    "subtotal": ("subtotal", "total cost", "cost"),
    "pct_change": ("percent change",),
}

TRAILER_LABELS = ("subtotal", "tax", "filtered total", "total")


class ParseError(RuntimeError):
    pass


@dataclass
class ServiceRow:
    service: str
    service_id: str = ""
    list_cost: float = 0.0
    negotiated: float = 0.0
    programmes: float = 0.0
    other_savings: float = 0.0
    subtotal: float = 0.0
    pct_change: str | None = None

    @property
    def savings(self) -> float:
        """Total savings applied to this service, as a negative number."""
        return self.negotiated + self.programmes + self.other_savings


@dataclass
class ServicesExport:
    rows: list[ServiceRow]
    currency: str = "EUR"
    reported_subtotal: float | None = None
    reported_tax: float | None = None
    reported_total: float | None = None
    source_name: str = ""

    @property
    def list_total(self) -> float:
        return sum(r.list_cost for r in self.rows)

    @property
    def savings_total(self) -> float:
        return sum(r.savings for r in self.rows)

    @property
    def subtotal(self) -> float:
        """Prefer the figure the export itself reports, else sum the rows."""
        if self.reported_subtotal is not None:
            return self.reported_subtotal
        return sum(r.subtotal for r in self.rows)


def _num(raw: str | None) -> float:
    """Parse a money cell. Handles thousands separators and empty cells."""
    if raw is None:
        return 0.0
    s = raw.strip().replace(" ", "")
    if not s or s in {"-", "--"}:
        return 0.0
    s = re.sub(r"[^\d,.\-+]", "", s)
    if not s or s in {"-", "+"}:
        return 0.0
    # 1.234,56 (European) vs 1,234.56 (US): the last separator is the decimal one.
    last_comma, last_dot = s.rfind(","), s.rfind(".")
    if last_comma > last_dot:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _map_columns(header: list[str]) -> dict[str, int]:
    """Locate each known column by header prefix, longest match wins."""
    norm = [h.strip().lower() for h in header]
    found: dict[str, int] = {}
    for key, prefixes in COLS.items():
        best: tuple[int, int] | None = None
        for i, h in enumerate(norm):
            for p in prefixes:
                if h.startswith(p) and (best is None or len(p) > best[1]):
                    best = (i, len(p))
        if best is not None:
            found[key] = best[0]
    # "Subtotal" also prefixes "Unrounded subtotal"; keep them distinct.
    if found.get("subtotal") == found.get("unrounded"):
        for i, h in enumerate(norm):
            if h.startswith("subtotal"):
                found["subtotal"] = i
                break
    if "service" not in found or "subtotal" not in found:
        raise ParseError(
            "could not find the 'Service description' and 'Subtotal' columns in "
            f"the export header: {header}"
        )
    return found


def _currency(header: list[str], idx: dict[str, int]) -> str:
    for key in ("subtotal", "list_cost"):
        if key in idx:
            m = CURRENCY_RE.search(header[idx[key]])
            if m:
                return m.group(1).strip()
    return "EUR"


def read_services_csv(path) -> ServicesExport:
    """Read a by-service Cloud Billing export into a ServicesExport."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ParseError(f"{path} is empty")

    idx = _map_columns(rows[0])
    out = ServicesExport(rows=[], currency=_currency(rows[0], idx),
                         source_name=str(path).rsplit("/", 1)[-1])

    def cell(r: list[str], key: str) -> str:
        i = idx.get(key)
        return r[i] if i is not None and i < len(r) else ""

    for r in rows[1:]:
        name = cell(r, "service").strip()
        if name:
            pct = cell(r, "pct_change").strip() or None
            out.rows.append(ServiceRow(
                service=name,
                service_id=cell(r, "service_id").strip(),
                list_cost=_num(cell(r, "list_cost")),
                negotiated=_num(cell(r, "negotiated")),
                programmes=_num(cell(r, "programmes")),
                other_savings=_num(cell(r, "other_savings")),
                subtotal=_num(cell(r, "subtotal")),
                pct_change=pct,
            ))
            continue
        # Trailer rows carry their label in whatever column is non-empty before
        # the value columns: ",,,,,Subtotal,111.956583,111.96".
        label = next((c.strip().lower() for c in r if c.strip()
                      and not re.fullmatch(r"[-+]?[\d.,]+", c.strip())), "")
        if not label.startswith(TRAILER_LABELS):
            continue
        value = _num(cell(r, "subtotal")) or _num(cell(r, "unrounded"))
        if label.startswith("filtered total") or label == "total":
            out.reported_total = value
        elif label.startswith("tax"):
            out.reported_tax = value
        elif label.startswith("subtotal"):
            out.reported_subtotal = value

    if not out.rows:
        raise ParseError(f"{path} contained a header but no service rows")
    out.rows.sort(key=lambda r: r.subtotal, reverse=True)
    return out


# --------------------------------------------------------------------- daily

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y",
                "%b %d, %Y", "%d %b %Y")


def parse_date(raw: str) -> dt.date | None:
    s = raw.strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class DailySeries:
    """Cost per day, optionally broken down per service."""
    totals: dict[dt.date, float] = field(default_factory=dict)
    per_service: dict[dt.date, dict[str, float]] = field(default_factory=dict)
    estimated: bool = False
    note: str = ""

    @property
    def days(self) -> list[dt.date]:
        return sorted(self.totals)

    @property
    def total(self) -> float:
        return sum(self.totals.values())

    def scaled_to(self, target: float) -> "DailySeries":
        """Rescale so the series matches a known subtotal.

        Used when the daily numbers are reconstructed rather than exported: the
        shape is trustworthy, the absolute level should come from the export.
        """
        if not self.totals or target <= 0:
            return self
        k = target / self.total
        if abs(k - 1.0) < 1e-9:
            return self
        return DailySeries(
            totals={d: v * k for d, v in self.totals.items()},
            per_service={d: {s: v * k for s, v in per.items()}
                         for d, per in self.per_service.items()},
            estimated=self.estimated,
            note=self.note,
        )


def read_daily_csv(path) -> DailySeries:
    """Read a daily Cloud Billing export.

    Accepts any export with a date column plus a cost column. When a service
    column is present the breakdown is kept so the trend can be stacked.
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh) if any(c.strip() for c in r)]
    if not rows:
        raise ParseError(f"{path} is empty")

    header = [h.strip().lower() for h in rows[0]]
    date_i = next((i for i, h in enumerate(header)
                   if h.startswith(("date", "day", "usage date", "invoice"))), None)
    if date_i is None:
        date_i = next((i for i, c in enumerate(rows[1])
                       if parse_date(c) is not None), None)
    if date_i is None:
        raise ParseError(f"no date column found in {path}")

    cost_i = None
    for want in ("subtotal", "cost (", "cost", "total"):
        cost_i = next((i for i, h in enumerate(header)
                       if h.startswith(want) and i != date_i), None)
        if cost_i is not None:
            break
    if cost_i is None:
        raise ParseError(f"no cost column found in {path}")
    svc_i = next((i for i, h in enumerate(header)
                  if h.startswith(("service description", "service"))), None)

    out = DailySeries()
    for r in rows[1:]:
        if date_i >= len(r):
            continue
        d = parse_date(r[date_i])
        if d is None:
            continue
        v = _num(r[cost_i] if cost_i < len(r) else "")
        out.totals[d] = out.totals.get(d, 0.0) + v
        if svc_i is not None and svc_i < len(r) and r[svc_i].strip():
            out.per_service.setdefault(d, {})
            name = r[svc_i].strip()
            out.per_service[d][name] = out.per_service[d].get(name, 0.0) + v
    if not out.totals:
        raise ParseError(f"{path} had no parsable dated rows")
    return out


def daily_from_config(entries: list[dict]) -> DailySeries:
    """Build a series from inline config entries: [{date, amount}, ...]."""
    out = DailySeries(estimated=True)
    for e in entries:
        d = parse_date(str(e["date"]))
        if d is None:
            raise ParseError(f"unparsable date in daily entry: {e!r}")
        out.totals[d] = out.totals.get(d, 0.0) + float(e["amount"])
    return out
