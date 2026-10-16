"""Turn a parsed billing export plus report config into one canonical model.

Every number the report shows is computed here, once. The renderer never does
arithmetic. That is deliberate: the 08/2026 report shipped a figure whose bar
contradicted a number in the surrounding text, and the only structural fix is a
single source of truth for the whole document.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass, field

from .parse import DailySeries, ServicesExport

PCT_RE = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*%")


def _pct(raw: str | None) -> float | None:
    if not raw:
        return None
    m = PCT_RE.search(raw)
    return float(m.group(1).replace(",", ".")) / 100.0 if m else None


def _days_in_month(d: dt.date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def _prev_period_days(start: dt.date, days_in_period: int) -> int:
    """Length of the period GCP compares against.

    For a calendar-month range the console compares against the previous
    calendar month, which is why a 16-day month-to-date shows deceptively mild
    percentages. Anything else falls back to the same length.
    """
    if start.day == 1 and days_in_period == _days_in_month(start):
        prev_end = start - dt.timedelta(days=1)
        return _days_in_month(prev_end)
    return days_in_period


@dataclass
class ServiceMetric:
    name: str
    subtotal: float
    list_cost: float
    savings: float
    share: float
    per_day: float
    projection: float
    reported_change: float | None = None
    previous_total: float | None = None
    change_per_day: float | None = None
    always_on: bool = False
    is_focus: bool = False
    color: str = "#80868b"
    marker: str = "dot"


@dataclass
class Cut:
    label: str
    subtotal: float
    share: float
    per_day: float
    projection: float
    members: list[str] = field(default_factory=list)


@dataclass
class Crossing:
    threshold: float
    amount: float
    date: dt.date
    cumulative: float
    budget_in_force: float


@dataclass
class BudgetView:
    amount: float
    effective_from: dt.date | None = None
    previous_amount: float | None = None
    thresholds: list[float] = field(default_factory=list)
    changed_mid_period: bool = False
    pct_actual: float = 0.0
    pct_forecast: float = 0.0
    pct_floor: float = 0.0
    crossings: list[Crossing] = field(default_factory=list)
    highest_threshold_crossed: float | None = None


@dataclass
class UnitRow:
    key: str
    label: str
    value: float
    projected_value: float | None
    focus_per_unit: float
    total_per_unit: float
    marginal_per_unit: float
    projected_total_per_unit: float | None


@dataclass
class DailyStats:
    burst_factor: float
    baseline: float
    baseline_days: int
    peak: float
    peak_date: dt.date
    peak_ratio: float
    trough: float
    trough_date: dt.date
    weekday_avg: float
    weekend_avg: float
    burst_days: list[dt.date]
    burst_total: float
    burst_excess: float


@dataclass
class Model:
    # identity
    title: str
    subtitle: str
    entity: str
    period_label: str
    currency: str
    symbol: str
    period_start: dt.date
    period_end: dt.date
    data_through: dt.date
    days_elapsed: int
    days_in_period: int
    days_remaining: int
    generated_on: dt.date
    # money
    list_total: float
    savings_total: float
    subtotal: float
    discount_pct: float
    tax: float
    per_day: float
    flat_projection: float
    forecast: float
    forecast_source: str
    forecast_is_external: bool
    implied_remaining_per_day: float
    # structure
    services: list[ServiceMetric]
    focus: Cut
    rest: Cut
    always_on: Cut
    usage_driven: Cut
    largest: ServiceMetric
    # optional blocks
    budget: BudgetView | None = None
    units: list[UnitRow] = field(default_factory=list)
    unit_source: str = ""
    unit_as_of: str = ""
    units_projected: bool = False
    marginal_label: str = ""
    marginal_total: float = 0.0
    daily: DailySeries | None = None
    daily_stats: DailyStats | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def focus_name(self) -> str:
        return self.focus.members[0] if self.focus.members else self.focus.label

    def money(self, v: float, dp: int = 2) -> str:
        return f"{self.symbol}{v:,.{dp}f}"


# GCP console palette, in the order the console assigns it.
PALETTE = [
    ("#4285f4", "circle"), ("#f4511e", "square"), ("#f9ab00", "diamond"),
    ("#34a853", "tri-down"), ("#a142f4", "tri-up"), ("#12b5cb", "pentagon"),
    ("#e8710a", "cross"), ("#9e9d24", "asterisk"), ("#7986cb", "shield"),
    ("#ec407a", "star"), ("#5f6368", "dot"), ("#80868b", "dot"),
]

SYMBOLS = {"EUR": "€", "€": "€", "USD": "$", "$": "$", "GBP": "£"}


def _match(name: str, wanted: list[str]) -> bool:
    n = name.strip().lower()
    return any(n == w.strip().lower() or n.startswith(w.strip().lower())
               for w in wanted)


def build(export: ServicesExport, cfg: dict,
          daily: DailySeries | None = None) -> Model:
    rep = cfg.get("report", {})
    start = _date(rep["period_start"])
    end = _date(rep["period_end"])
    through = _date(rep.get("data_through") or rep["period_end"])
    days_in_period = (end - start).days + 1
    days_elapsed = (through - start).days + 1
    if days_elapsed < 1 or days_elapsed > days_in_period:
        raise ValueError(
            f"data_through {through} is outside {start}..{end}")

    currency = rep.get("currency") or export.currency
    symbol = rep.get("currency_symbol") or SYMBOLS.get(currency, currency + " ")

    subtotal = export.subtotal
    list_total = export.list_total
    savings = export.savings_total
    if abs(list_total + savings - subtotal) > max(0.05, subtotal * 0.002):
        # Not fatal: some exports omit a savings column. Record it instead of
        # silently publishing a reconciliation that does not add up.
        pass

    focus_cfg = cfg.get("focus", {}) or {}
    focus_names = focus_cfg.get("services") or (
        [focus_cfg["service"]] if focus_cfg.get("service") else [])
    always_names = cfg.get("always_on", []) or []
    prev_days = _prev_period_days(start, days_in_period)
    scale = days_in_period / days_elapsed

    services: list[ServiceMetric] = []
    for i, r in enumerate(export.rows):
        color, marker = PALETTE[min(i, len(PALETTE) - 1)]
        change = _pct(r.pct_change)
        prev_total = None
        change_pd = None
        if change is not None and change > -1.0:
            prev_total = r.subtotal / (1.0 + change)
            if prev_days > 0:
                prev_pd = prev_total / prev_days
                cur_pd = r.subtotal / days_elapsed
                if prev_pd:
                    change_pd = cur_pd / prev_pd - 1.0
                elif not cur_pd:
                    change_pd = 0.0
        services.append(ServiceMetric(
            name=r.service,
            subtotal=r.subtotal,
            list_cost=r.list_cost,
            savings=r.savings,
            share=(r.subtotal / subtotal) if subtotal else 0.0,
            per_day=r.subtotal / days_elapsed,
            projection=r.subtotal * scale,
            reported_change=change,
            previous_total=prev_total,
            change_per_day=change_pd,
            always_on=_match(r.service, always_names),
            is_focus=_match(r.service, focus_names),
            color=color,
            marker=marker,
        ))

    def cut(label: str, picked: list[ServiceMetric],
            complement_of: float | None = None) -> Cut:
        # A complement is derived from the subtotal rather than summed from
        # rounded rows, so focus plus rest is exactly the subtotal.
        s = (subtotal - complement_of) if complement_of is not None \
            else sum(m.subtotal for m in picked)
        return Cut(label=label, subtotal=s,
                   share=(s / subtotal) if subtotal else 0.0,
                   per_day=s / days_elapsed, projection=s * scale,
                   members=[m.name for m in picked])

    focus_ms = [m for m in services if m.is_focus]
    if not focus_ms:
        raise ValueError(
            "focus.service did not match any service in the export. Present: "
            + ", ".join(m.name for m in services))
    focus = cut(focus_cfg.get("label") or focus_ms[0].name, focus_ms)
    rest = cut(cfg.get("rest_label", "Everything else"),
               [m for m in services if not m.is_focus],
               complement_of=focus.subtotal)
    always = cut("Always-on", [m for m in services if m.always_on])
    usage = cut("Usage-driven", [m for m in services if not m.always_on],
                complement_of=always.subtotal)

    flat = subtotal * scale
    fc_cfg = cfg.get("forecast", {}) or {}
    forecast = float(fc_cfg["value"]) if fc_cfg.get("value") else flat
    days_remaining = days_in_period - days_elapsed
    implied = ((forecast - subtotal) / days_remaining) if days_remaining else 0.0

    m = Model(
        title=rep.get("title", "Cloud cost report"),
        subtitle=rep.get("subtitle", "Executive summary"),
        entity=rep.get("entity", ""),
        period_label=rep.get("period_label", f"{start} to {end}"),
        currency=currency, symbol=symbol,
        period_start=start, period_end=end, data_through=through,
        days_elapsed=days_elapsed, days_in_period=days_in_period,
        days_remaining=days_remaining,
        generated_on=_date(rep["generated_on"]) if rep.get("generated_on") else through,
        list_total=list_total, savings_total=savings, subtotal=subtotal,
        discount_pct=(-savings / list_total) if list_total else 0.0,
        tax=export.reported_tax or 0.0,
        per_day=subtotal / days_elapsed,
        flat_projection=flat,
        forecast=forecast,
        forecast_source=fc_cfg.get("source", "straight line from the period to date"),
        forecast_is_external=bool(fc_cfg.get("value")),
        implied_remaining_per_day=implied,
        services=services, focus=focus, rest=rest,
        always_on=always, usage_driven=usage,
        largest=max(services, key=lambda s: s.subtotal),
    )

    if daily is not None:
        m.daily = daily.scaled_to(subtotal) if daily.estimated else daily
        m.daily_stats = _daily_stats(m.daily)

    if cfg.get("budget"):
        m.budget = _budget(cfg["budget"], m)

    if cfg.get("usage"):
        _units(cfg["usage"], m)

    m.notes = _notes(m, export)
    return m


def _date(v) -> dt.date:
    if isinstance(v, dt.date):
        return v
    return dt.datetime.strptime(str(v), "%Y-%m-%d").date()


def _daily_stats(d: DailySeries) -> DailyStats | None:
    days = d.days
    if len(days) < 3:
        return None
    vals = [d.totals[x] for x in days]
    wk = [d.totals[x] for x in days if x.weekday() < 5]
    we = [d.totals[x] for x in days if x.weekday() >= 5]
    peak_date = max(days, key=lambda x: d.totals[x])
    trough_date = min(days, key=lambda x: d.totals[x])
    # Baseline: the median of the cheapest 60% of days, which ignores bursts
    # without hand-picking a window.
    ordered = sorted(vals)
    cheap = ordered[: max(2, int(len(ordered) * 0.6))]
    baseline = cheap[len(cheap) // 2] if len(cheap) % 2 else (
        (cheap[len(cheap) // 2 - 1] + cheap[len(cheap) // 2]) / 2)
    burst = [x for x in days if d.totals[x] > baseline * 1.35]
    burst_total = sum(d.totals[x] for x in burst)
    return DailyStats(
        burst_factor=1.35,
        baseline=baseline, baseline_days=len(cheap),
        peak=d.totals[peak_date], peak_date=peak_date,
        peak_ratio=(d.totals[peak_date] / baseline) if baseline else 0.0,
        trough=d.totals[trough_date], trough_date=trough_date,
        weekday_avg=(sum(wk) / len(wk)) if wk else 0.0,
        weekend_avg=(sum(we) / len(we)) if we else 0.0,
        burst_days=burst, burst_total=burst_total,
        burst_excess=burst_total - baseline * len(burst),
    )


def _budget(bcfg: dict, m: Model) -> BudgetView:
    amount = float(bcfg["amount"])
    prev = bcfg.get("previous_amount")
    eff = _date(bcfg["effective_from"]) if bcfg.get("effective_from") else None
    b = BudgetView(
        amount=amount,
        effective_from=eff,
        previous_amount=float(prev) if prev is not None else None,
        thresholds=[float(t) for t in bcfg.get("alert_thresholds",
                                               [0.5, 0.75, 0.9, 1.0])],
        changed_mid_period=bool(prev is not None and eff
                                and m.period_start <= eff <= m.period_end),
        pct_actual=m.subtotal / amount if amount else 0.0,
        pct_forecast=m.forecast / amount if amount else 0.0,
        pct_floor=m.always_on.projection / amount if amount else 0.0,
    )
    if m.daily:
        b.crossings = _crossings(m.daily, b)
        if b.crossings:
            b.highest_threshold_crossed = max(c.threshold for c in b.crossings)
    return b


def _crossings(d: DailySeries, b: BudgetView) -> list[Crossing]:
    """When cumulative spend crossed each alert threshold.

    The budget in force on each day is used, so a mid-period budget change does
    not retroactively rewrite which alerts actually fired.
    """
    out: list[Crossing] = []
    cum = 0.0
    hit: set[float] = set()
    for day in d.days:
        cum += d.totals[day]
        in_force = b.amount
        if b.previous_amount is not None and b.effective_from and day < b.effective_from:
            in_force = b.previous_amount
        for t in sorted(b.thresholds):
            amount = in_force * t
            if t not in hit and cum >= amount:
                hit.add(t)
                out.append(Crossing(threshold=t, amount=amount, date=day,
                                    cumulative=cum, budget_in_force=in_force))
    return out


def _units(ucfg: dict, m: Model) -> None:
    marginal_names = ucfg.get("marginal_services") or []
    marginal = sum(s.subtotal for s in m.services
                   if _match(s.name, marginal_names)) or m.focus.subtotal
    m.marginal_total = marginal
    m.marginal_label = " plus ".join(
        s.name for s in m.services if _match(s.name, marginal_names)) or m.focus.label
    m.unit_source = ucfg.get("source", "")
    m.unit_as_of = str(ucfg.get("as_of", ""))
    m.units_projected = bool(ucfg.get("counters_are_period_to_date", True))
    scale = m.days_in_period / m.days_elapsed

    for c in ucfg.get("counters", []):
        v = float(c["value"])
        if v <= 0:
            continue
        proj = v * scale if (m.units_projected and c.get("scales", True)) else None
        m.units.append(UnitRow(
            key=c.get("key", c["label"]),
            label=c["label"],
            value=v,
            projected_value=proj,
            focus_per_unit=m.focus.subtotal / v,
            total_per_unit=m.subtotal / v,
            marginal_per_unit=marginal / v,
            projected_total_per_unit=(m.forecast / proj) if proj else (
                m.forecast / v),
        ))


def _notes(m: Model, export: ServicesExport) -> list[str]:
    """Facts the reader needs to interpret the numbers. No proposals."""
    n = [
        f"Figures are subtotals after {m.discount_pct * 100:.1f}% savings applied "
        f"to a list price of {m.money(m.list_total)}.",
        f"The period runs {m.period_start:%d %b} to {m.period_end:%d %b %Y}; "
        f"actual cost covers {m.days_elapsed} complete "
        f"{'day' if m.days_elapsed == 1 else 'days'} through "
        f"{m.data_through:%d %b}, at {m.money(m.per_day, 3)} per day.",
    ]
    if m.forecast_is_external:
        n.append(
            f"The {m.money(m.forecast)} forecast is the {m.forecast_source}. It "
            f"implies {m.money(m.implied_remaining_per_day, 3)} per day for the "
            f"remaining {m.days_remaining} days, against "
            f"{m.money(m.per_day, 3)} per day observed so far.")
    if any(s.reported_change is not None for s in m.services):
        prev_days = _prev_period_days(m.period_start, m.days_in_period)
        if prev_days != m.days_elapsed:
            n.append(
                f"The reported change compares {m.days_elapsed} days of this "
                f"period against {prev_days} days of the previous one, so it is "
                f"not like-for-like and can point the wrong way: a service that "
                f"reports no change is in fact spending more per day, and one "
                f"that reports a fall may have fallen less than it appears. The "
                f"change-per-day column restates both periods as a daily rate, "
                f"which is comparable.")
    if m.budget and m.budget.changed_mid_period:
        n.append(
            f"The budget changed inside the period: "
            f"{m.money(m.budget.previous_amount, 0)} until "
            f"{m.budget.effective_from:%d %b}, "
            f"{m.money(m.budget.amount, 0)} after. "
            f"Alert thresholds are evaluated against the budget in force on each "
            f"day.")
    if m.daily and m.daily.estimated:
        n.append(
            "The daily series is reconstructed rather than exported, and is "
            "rescaled so it sums to the reported subtotal. Read day-level values "
            "as approximate; the totals are exact.")
    if m.units and m.units_projected:
        n.append(
            f"Per-unit costs use volumes reported "
            + (f"by {m.unit_source} " if m.unit_source else "")
            + f"for the same window. Projected per-unit costs scale volume with "
            f"elapsed days.")
    if export.reported_tax:
        n.append(f"Tax of {m.money(export.reported_tax)} is included.")
    return n
