"""Assemble the executive report as one self-contained, print-ready HTML file.

Layout rules that matter for the PDF:
  * one <section class="page"> per printed page, break-after: page
  * cards, figures, tables and rows never break inside
  * table headers repeat if a table ever does span pages
  * the page footer is written at render time, so the page count in the document
    is only correct if no section overflows. generate.py verifies that against
    the real PDF instead of trusting it.
"""
from __future__ import annotations

import datetime as dt
import sys

from . import charts
from .metrics import Model

EM_DASH = "\u2014"  # written as an escape so the source never contains the character
INTERNAL_HINTS = ("bitbucket.org", "github.com", "pull-request", ".yaml", ".toml",
                  ".tf", "terraform", "git commit", "localhost", "10.")


def sanitize(s: str, where: str = "") -> str:
    """Strip characters the report forbids and warn on internal leakage."""
    out = str(s)
    if EM_DASH in out:
        out = out.replace(EM_DASH, " - ")
    low = out.lower()
    for hint in INTERNAL_HINTS:
        if hint in low:
            print(f"warning: {where or 'text'} looks internal ({hint!r}); an "
                  f"executive report should not carry it", file=sys.stderr)
            break
    return out


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def cap(s: str) -> str:
    s = str(s).strip()
    return (s[0].upper() + s[1:]) if s else s


def pct(v: float, dp: int = 1) -> str:
    return f"{v * 100:.{dp}f}%"


def signed_pct(v: float | None, dp: int = 0) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:+.{dp}f}%"


CSS = """
:root{
  --ink:#202124; --dim:#5f6368; --faint:#5f6368; --rule:#dadce0;
  --panel:#f6f8fa; --panel-2:#eef1f5; --accent:#1a73e8; --warn:#d93025;
  --ok:#188038; --focus:#f4511e;
}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{
  margin:0; background:#fff; color:var(--ink);
  font-family:"Helvetica Neue",Helvetica,Arial,"Liberation Sans",sans-serif;
  font-size:10.5pt; line-height:1.45;
}
.page{
  position:relative; padding:0 0 16mm 0; max-width:186mm; margin:0 auto 10mm;
}
h1{font-size:20pt; line-height:1.15; margin:0 0 2mm; letter-spacing:-.2pt}
h2{font-size:13pt; margin:0 0 1mm; letter-spacing:-.1pt}
h3{font-size:10.5pt; margin:0 0 1mm; text-transform:uppercase;
   letter-spacing:.6pt; color:var(--dim)}
p{margin:0 0 2.4mm}
.lead{font-size:11pt}
.muted{color:var(--dim)}
.small{font-size:8.6pt; line-height:1.4}
.mono{font-variant-numeric:tabular-nums;
      font-family:"SFMono-Regular",Menlo,Consolas,"Liberation Mono",monospace}
.num{font-variant-numeric:tabular-nums}

/* masthead */
.masthead{border-top:3px solid var(--ink); padding-top:3mm; margin-bottom:5mm}
.masthead .row{display:flex; justify-content:space-between; align-items:flex-end;
               gap:8mm}
.masthead .meta{text-align:right; font-size:8.6pt; color:var(--dim);
                line-height:1.5; white-space:nowrap}
.eyebrow{font-size:8.4pt; text-transform:uppercase; letter-spacing:1.1pt;
         color:var(--dim); margin:0 0 1.5mm}

/* verdict */
.verdict{border-left:3px solid var(--focus); background:var(--panel);
         padding:3.5mm 4mm; margin:0 0 5mm}
.verdict .headline{font-size:12.5pt; font-weight:700; line-height:1.3;
                   margin:0 0 1.5mm}
.verdict p:last-child{margin:0}

/* kpi */
.kpis{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:3mm;
      margin:0 0 5mm}
.kpi{border:1px solid var(--rule); border-top:3px solid var(--accent);
     padding:3mm 3mm 2.6mm; background:#fff}
.kpi.focus{border-top-color:var(--focus)}
.kpi.warn{border-top-color:var(--warn)}
.kpi.ok{border-top-color:var(--ok)}
.kpi .label{font-size:8.2pt; color:var(--dim); text-transform:uppercase;
            letter-spacing:.5pt; margin:0 0 1.5mm; line-height:1.25;
            min-height:7.4mm}
.kpi .value{font-size:17pt; font-weight:700; line-height:1;
            font-variant-numeric:tabular-nums; letter-spacing:-.4pt}
.kpi .sub{font-size:8.2pt; color:var(--dim); margin-top:1.6mm; line-height:1.3}

/* generic blocks */
.block{margin:0 0 5mm}
.grid-2{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:5mm}
.grid-2.wide-left{grid-template-columns:minmax(0,1.25fr) minmax(0,1fr)}
.grid-3{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:3mm}
.panel{background:var(--panel); border:1px solid var(--rule); padding:3mm}
.stat{background:var(--panel); border:1px solid var(--rule); padding:3mm}
.stat .k{font-size:8.2pt; color:var(--dim); text-transform:uppercase;
         letter-spacing:.5pt}
.stat .v{font-size:14pt; font-weight:700; font-variant-numeric:tabular-nums;
         line-height:1.15; margin-top:1mm}
.stat .n{font-size:8.2pt; color:var(--dim); margin-top:.8mm}
figure{margin:0}
figcaption{font-size:8.4pt; color:var(--dim); margin-top:1.5mm}
.chart{display:block; width:100%; height:auto}
.inline-bar{display:block}
.reading{font-size:9.6pt; border-top:1px solid var(--rule); padding-top:2mm;
         margin-top:2mm}
.reading b{font-weight:700}

/* tables */
table{width:100%; border-collapse:collapse; font-size:9pt}
caption{text-align:left; font-size:8.4pt; color:var(--dim); padding-bottom:1.5mm}
th{font-size:7.6pt; text-transform:uppercase; letter-spacing:.35pt;
   color:var(--dim); font-weight:700; text-align:right; padding:1.4mm 1.2mm;
   border-bottom:1px solid var(--ink); vertical-align:bottom; line-height:1.2}
th.l,td.l{text-align:left}
td{padding:1.4mm 1.2mm; text-align:right; border-bottom:1px solid var(--rule);
   font-variant-numeric:tabular-nums; white-space:nowrap}
td.l{white-space:normal}
table.services th:first-child{width:25%}
table.services th:nth-child(2),table.services td:nth-child(2){width:9%;
   overflow:hidden}
table.services td.l{white-space:normal; line-height:1.25}
tbody tr:nth-child(even){background:#fafbfc}
tr.total td{border-top:1.5px solid var(--ink); border-bottom:none;
            font-weight:700; background:#fff}
td.svc{display:flex; align-items:center; gap:2mm; text-align:left}
td.svc svg{flex:0 0 auto}
.up{color:var(--warn)} .down{color:var(--ok)} .flat{color:var(--faint)}
.ao{font-size:7.4pt; color:var(--faint); margin-left:.8mm; vertical-align:super}
.tablenote{font-size:8pt; color:var(--dim); margin-top:1.5mm}

/* footer */
.foot{position:absolute; bottom:4mm; left:0; right:0;
      border-top:1px solid var(--rule); padding-top:1.6mm;
      display:flex; justify-content:space-between;
      font-size:7.8pt; color:var(--faint)}

@page{size:A4 portrait; margin:13mm 12mm 12mm 12mm}
@media print{
  body{font-size:9.6pt}
  .page{page-break-after:always; break-after:page; margin:0;
        padding:0 1mm 13mm 0; height:270mm; max-width:none; overflow:visible}
  .page:last-of-type{page-break-after:auto; break-after:auto}
  .kpi,.stat,.panel,figure,table,.verdict,.reading{page-break-inside:avoid;
        break-inside:avoid}
  tr,thead{page-break-inside:avoid; break-inside:avoid}
  thead{display:table-header-group}
  h1,h2,h3{page-break-after:avoid; break-after:avoid}
}
@media screen{
  body{background:#eceff3; padding:8mm 4mm}
  .page{background:#fff; box-shadow:0 1px 4px rgba(0,0,0,.16);
        padding:10mm 10mm 18mm; min-height:262mm}
}
"""


class Report:
    def __init__(self, m: Model):
        self.m = m
        self.pages: list[str] = []

    # ---------------------------------------------------------------- helpers
    def money(self, v: float, dp: int = 2) -> str:
        sign = "-" if v < 0 else ""
        return f"{sign}{self.m.symbol}{abs(v):,.{dp}f}"

    def unit_money(self, v: float) -> str:
        """One precision for per-unit money, wherever it is printed."""
        return self.money(v, 4 if abs(v) < 1 else 3)

    def rate(self, v: float) -> str:
        """One precision for per-day rates, wherever they are printed."""
        return self.money(v, 3)

    def _masthead(self) -> str:
        m = self.m
        return f"""<header class="masthead">
  <p class="eyebrow">{esc(sanitize(m.subtitle))}</p>
  <div class="row">
    <div>
      <h1>{esc(sanitize(m.title))}</h1>
      <p class="muted small" style="margin:0">{esc(m.entity)}</p>
    </div>
    <div class="meta">
      <div><b>{esc(m.period_label)}</b></div>
      <div>Actual to {m.data_through:%d %b %Y} · {m.days_elapsed} of
        {m.days_in_period} days</div>
      <div>Currency {esc(m.currency)} · issued {m.generated_on:%d %b %Y}</div>
    </div>
  </div>
</header>"""

    def _kpis(self) -> str:
        m = self.m
        tiles = [
            ("", "Actual, period to date", self.money(m.subtotal),
             f"{m.days_elapsed} complete days at {self.rate(m.per_day)} per day"),
            ("focus", f"Forecast, {m.period_end:%d %b}", self.money(m.forecast),
             sanitize(m.forecast_source)),
            ("", f"{esc(m.focus.label)} share", pct(m.focus.share),
             f"{self.money(m.focus.subtotal)} of {self.money(m.subtotal)}"),
        ]
        if m.budget:
            cls = "warn" if m.budget.pct_forecast > 1 else "ok"
            tiles.append((cls, "Monthly budget", self.money(m.budget.amount, 0),
                          f"forecast at {pct(m.budget.pct_forecast, 0)} of budget"))
        else:
            tiles.append(("", "Largest service", self.money(m.largest.subtotal),
                          f"{esc(m.largest.name)}, {pct(m.largest.share)} of spend"))
        cells = "".join(
            f'<div class="kpi {c}"><div class="label">{esc(l)}</div>'
            f'<div class="value">{esc(v)}</div>'
            f'<div class="sub">{esc(s)}</div></div>'
            for c, l, v, s in tiles)
        return f'<div class="kpis">{cells}</div>'

    def _verdict(self) -> str:
        m = self.m
        ratio = (m.largest.subtotal / m.focus.subtotal) if m.focus.subtotal else 0
        head = (f"{m.focus.label} is {pct(m.focus.share)} of the bill. "
                f"{m.rest.label.lower().capitalize()} is {pct(m.rest.share)}.")
        lines = []
        if m.largest.name not in m.focus.members:
            lines.append(
                f"{esc(m.largest.name)} is the largest single line at "
                f"{self.money(m.largest.subtotal)} ({pct(m.largest.share)} of "
                f"spend), {ratio:.1f} times the {esc(m.focus.label)} bill.")
        else:
            lines.append(
                f"{esc(m.largest.name)} is both the focus of this report and the "
                f"largest line at {pct(m.largest.share)} of spend.")
        lines.append(
            f"{pct(m.always_on.share)} of the spend is always-on capacity, "
            f"{self.money(m.always_on.projection)} per month at the current "
            f"shape, billed whether the product is used or not. The remaining "
            f"{pct(m.usage_driven.share)} follows usage.")
        if m.budget:
            verb = "above" if m.budget.pct_forecast > 1 else "inside"
            lines.append(
                f"The period is forecast to close at {self.money(m.forecast)}, "
                f"{verb} the {self.money(m.budget.amount, 0)} budget "
                f"({pct(m.budget.pct_forecast, 0)}).")
        body = "".join(f"<p>{t}</p>" for t in lines)
        return (f'<div class="verdict"><p class="headline">{esc(head)}</p>'
                f'{body}</div>')

    # ------------------------------------------------------------------ pages
    def page_headline(self) -> str:
        m = self.m
        segs = self._mix_segments()
        left = charts.donut(segs, m.subtotal, m.symbol,
                            f"{m.days_elapsed} days to {m.data_through:%d %b}",
                            300, 268)
        right = charts.legend(segs, m.subtotal, m.symbol, 300)
        split = charts.split_bar(
            [(m.focus.label, m.focus.subtotal, "#f4511e"),
             (m.rest.label, m.rest.subtotal, "#4285f4")],
            m.subtotal, m.symbol, 600, 62)
        return f"""{self._masthead()}
{self._kpis()}
{self._verdict()}
<div class="block">
  <h2>Where the money went</h2>
  <div class="grid-2 wide-left">
    <figure>{left}</figure>
    <div>
      <h3>By service</h3>
      {right}
    </div>
  </div>
</div>
<div class="block">
  <h3>{esc(m.focus.label)} against everything else</h3>
  <figure>{split}
    <figcaption>Share of the {esc(self.money(m.subtotal))} period subtotal.
      {self._focus_members_note()}</figcaption>
  </figure>
</div>"""

    def _focus_definition(self) -> str:
        """Never restate the label as its own definition."""
        m = self.m
        members = m.focus.members
        if len(members) == 1 and members[0].strip().lower() == \
                m.focus.label.strip().lower():
            return ("The service this report isolates, separated from every "
                    "other billed service")
        return esc(", ".join(members))

    def _focus_members_note(self) -> str:
        """Only worth a sentence when the label hides more than one service."""
        m = self.m
        members = m.focus.members
        if len(members) == 1 and members[0].strip().lower() == \
                m.focus.label.strip().lower():
            n = len([s for s in m.services if not s.is_focus
                     and (round(s.subtotal, 2) > 0 or round(s.list_cost, 2) > 0)])
            return (f"{esc(m.rest.label)} is every other billed service, "
                    f"{n} in total.")
        return f"{esc(m.focus.label)} covers {esc(', '.join(members))}."

    def _mix_segments(self):
        """Top services by value, with a rolled-up tail so the donut stays legible."""
        m = self.m
        top = [s for s in m.services if s.share >= 0.01][:7]
        segs = [(s.name, s.subtotal, s.color) for s in top]
        tail = m.subtotal - sum(s.subtotal for s in top)
        if tail > 0.005:
            segs.append(("Other services", tail, "#bdc1c6"))
        return segs

    def page_services(self) -> str:
        m = self.m
        billed = [s for s in m.services if round(s.subtotal, 2) > 0
                  or round(s.list_cost, 2) > 0]
        skipped = len(m.services) - len(billed)
        mx = max(s.subtotal for s in billed) if billed else 0.0
        rows = []
        for s in billed:
            chg = signed_pct(s.reported_change)
            chg_pd = signed_pct(s.change_per_day)
            cls = ("up" if (s.change_per_day or 0) > 0.005 else
                   "down" if (s.change_per_day or 0) < -0.005 else "flat")
            tag = '<span class="ao">A</span>' if s.always_on else ""
            focus = ' style="font-weight:700"' if s.is_focus else ""
            rows.append(
                f'<tr{focus}><td class="l"><span style="display:inline-flex;'
                f'align-items:center;gap:1.6mm">'
                f'<svg width="12" height="12" viewBox="0 0 12 12" '
                f'xmlns="http://www.w3.org/2000/svg">'
                f'{charts.marker(6, 6, s.marker, s.color, 4.6)}</svg>'
                f'{esc(s.name)}{tag}</span></td>'
                f'<td>{charts.inline_bar(s.subtotal, mx, s.color)}</td>'
                f'<td>{self.money(s.list_cost)}</td>'
                f'<td class="down">{self.money(s.savings)}</td>'
                f'<td><b>{self.money(s.subtotal)}</b></td>'
                f'<td>{pct(s.share)}</td>'
                f'<td>{self.money(s.per_day, 3)}</td>'
                f'<td>{self.money(s.projection)}</td>'
                f'<td class="flat">{chg}</td>'
                f'<td class="{cls}">{chg_pd}</td></tr>')
        total = (
            f'<tr class="total"><td class="l">Subtotal</td><td></td>'
            f'<td>{self.money(m.list_total)}</td>'
            f'<td>{self.money(m.savings_total)}</td>'
            f'<td>{self.money(m.subtotal)}</td><td>100.0%</td>'
            f'<td>{self.money(m.per_day, 3)}</td>'
            f'<td>{self.money(m.flat_projection)}</td><td></td><td></td></tr>')
        skipped_note = (f" {skipped} further "
                        f"{'service' if skipped == 1 else 'services'} carried no "
                        f"charge in the period and are omitted." if skipped else "")
        bars = charts.hbars(
            [(s.name, s.subtotal, s.color, pct(s.share)) for s in billed
             if s.subtotal > 0][:9], m.symbol, 600, 24)
        return f"""<h2>Cost breakdown by service</h2>
<p class="muted small">Every service billed in the period, ordered by subtotal.
  Savings are already applied; the projection extends the period-to-date rate to
  all {m.days_in_period} days.</p>
<div class="block">
<table class="services">
  <thead><tr>
    <th class="l">Service</th><th></th><th>List</th><th>Savings</th>
    <th>Subtotal</th><th>Mix</th><th>Per<br>day</th>
    <th>Projected</th><th>Reported<br>change</th><th>Change<br>per day</th>
  </tr></thead>
  <tbody>{"".join(rows)}{total}</tbody>
</table>
<p class="tablenote"><span class="ao">A</span> billed around the clock
  regardless of usage. Reported change is what the console shows against the
  previous period; change per day restates both periods as a daily rate, which is
  the only like-for-like comparison while the current period is incomplete.{skipped_note}</p>
</div>
<div class="block">
  <h3>Relative weight</h3>
  <figure>{bars}<figcaption>The {len([s for s in billed if s.subtotal > 0][:9])}
    largest services by subtotal, with each share of the period total.
  </figcaption></figure>
</div>"""

    def page_behaviour(self) -> str:
        m = self.m
        split = charts.split_bar(
            [(m.always_on.label, m.always_on.subtotal, "#5f6368"),
             (m.usage_driven.label, m.usage_driven.subtotal, "#1a73e8")],
            m.subtotal, m.symbol, 600, 62)
        cards = f"""<div class="grid-3">
  <div class="stat"><div class="k">Always-on</div>
    <div class="v">{self.money(m.always_on.subtotal)}</div>
    <div class="n">{pct(m.always_on.share)} of the spend ·
      {self.money(m.always_on.projection)} projected</div></div>
  <div class="stat"><div class="k">Usage-driven</div>
    <div class="v">{self.money(m.usage_driven.subtotal)}</div>
    <div class="n">{pct(m.usage_driven.share)} of the spend ·
      {self.money(m.usage_driven.projection)} projected</div></div>
  <div class="stat"><div class="k">Of which {esc(m.focus.label)}</div>
    <div class="v">{self.money(m.focus.subtotal)}</div>
    <div class="n">{pct(m.focus.share)} of the spend, inside usage-driven ·
      {self.money(m.focus.projection)} projected</div></div>
</div>"""
        trend = self._trend_block()
        return f"""<h2>How the cost behaves</h2>
<p class="muted small">The same money cut by billing behaviour rather than by
  product area: capacity that bills around the clock against consumption that
  only bills when work runs.</p>
<div class="block">{cards}</div>
<div class="block">
  <figure>{split}
    <figcaption>Always-on covers {esc(", ".join(m.always_on.members) or "no services")}.
    </figcaption></figure>
</div>
{trend}"""

    def _trend_block(self) -> str:
        m = self.m
        if not m.daily:
            return ""
        days = m.daily.days
        vals = [m.daily.totals[d] for d in days]
        projected = []
        if m.days_remaining > 0 and m.implied_remaining_per_day > 0:
            d = m.data_through
            for _ in range(m.days_remaining):
                d = d + dt.timedelta(days=1)
                projected.append((d, m.implied_remaining_per_day))
        base = m.daily_stats.baseline if m.daily_stats else None
        svg = charts.daily_columns(days, vals, m.symbol, base, projected, 600, 210)
        stats = ""
        if m.daily_stats:
            s = m.daily_stats
            stats = f"""<table>
  <caption>Daily distribution over the {len(days)} days of actual cost.</caption>
  <thead><tr><th class="l">Measure</th><th>Value</th><th class="l">Read</th>
  </tr></thead>
  <tbody>
    <tr><td class="l">Baseline day</td><td>{self.money(s.baseline)}</td>
      <td class="l">Median of the {s.baseline_days} cheapest days</td></tr>
    <tr><td class="l">Peak day</td><td>{self.money(s.peak)}</td>
      <td class="l">{s.peak_date:%d %b}, {s.peak_ratio:.1f} times baseline</td></tr>
    <tr><td class="l">Cheapest day</td><td>{self.money(s.trough)}</td>
      <td class="l">{s.trough_date:%d %b}</td></tr>
    <tr><td class="l">Weekday average</td><td>{self.money(s.weekday_avg)}</td>
      <td class="l">Monday to Friday</td></tr>
    <tr><td class="l">Weekend average</td><td>{self.money(s.weekend_avg)}</td>
      <td class="l">The level reached with the team away</td></tr>
    <tr><td class="l">Burst days</td><td>{len(s.burst_days)}</td>
      <td class="l">Above {s.burst_factor:.2f} times baseline, carrying
        {self.money(s.burst_excess)} over it</td></tr>
  </tbody></table>"""
        note = ""
        if m.daily.estimated:
            note = ("Day-level values are reconstructed and rescaled to the "
                    "reported subtotal, so read them as approximate. ")
        return f"""<div class="block">
  <h3>Daily trend</h3>
  <figure>{svg}
    <figcaption>{esc(note)}Blue: at or near baseline. Orange: above baseline.
      Grey: the remaining {m.days_remaining} days at the forecast rate of
      {esc(self.rate(m.implied_remaining_per_day))} per day.</figcaption>
  </figure>
</div>
<div class="block">{stats}</div>"""

    def page_units(self) -> str:
        m = self.m
        if not m.units:
            return ""
        tiles = "".join(
            f'<div class="stat"><div class="k">{esc(u.label)}</div>'
            f'<div class="v">{u.value:,.0f}</div>'
            f'<div class="n">' +
            (f"{u.projected_value:,.0f} projected by "
             f"{m.period_end:%d %b}" if u.projected_value else "reported volume")
            + "</div></div>"
            for u in m.units)
        head = "".join(f"<th>Per {esc(u.label.rstrip('s'))}</th>" for u in m.units)

        def row(label: str, amount: float, pick, note: str, strong=False) -> str:
            cells = "".join(f"<td>{'<b>' if strong else ''}"
                            f"{self.unit_money(pick(u))}"
                            f"{'</b>' if strong else ''}</td>" for u in m.units)
            return (f'<tr><td class="l"><b>{esc(label)}</b><br>'
                    f'<span class="small muted">{esc(note)}</span></td>'
                    f'<td>{self.money(amount)}</td>{cells}</tr>')

        rows = [
            row(m.focus.label, m.focus.subtotal, lambda u: u.focus_per_unit,
                "the focus of this report", True),
            row("All services", m.subtotal, lambda u: u.total_per_unit,
                "fully loaded, infrastructure included", True),
            row(m.marginal_label or m.focus.label, m.marginal_total,
                lambda u: u.marginal_per_unit,
                "the part that grows with one more unit of work"),
        ]
        proj = "".join(f"<td>{self.unit_money(u.projected_total_per_unit)}</td>"
                       for u in m.units)
        rows.append(
            f'<tr><td class="l"><b>Projected, all services</b><br>'
            f'<span class="small muted">the forecast spread over the whole '
            f'period</span></td><td>{self.money(m.forecast)}</td>{proj}</tr>')
        src = f" reported by {esc(m.unit_source)}" if m.unit_source else ""
        asof = f" as of {esc(m.unit_as_of)}" if m.unit_as_of else ""
        return f"""<h2>Unit economics</h2>
<p class="muted small">Period cost divided by the volumes{src}{asof}. The same
  money expressed in the units the business plans with.</p>
<div class="block"><div class="grid-3">{tiles}</div></div>
<div class="block">
<table>
  <thead><tr><th class="l">Cost basis</th><th>Period total</th>{head}</tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>
</div>
<div class="block reading">
  {self._unit_reading()}
</div>
{self._unit_charts()}"""

    def _unit_reading(self) -> str:
        """Highest-volume counter reads as efficiency, lowest as overhead."""
        m = self.m
        if not m.units:
            return ""
        fine = max(m.units, key=lambda u: u.value)
        coarse = min(m.units, key=lambda u: u.value)
        parts = [
            f"<b>One {fine.label.rstrip('s')} costs "
            f"{self.unit_money(fine.focus_per_unit)} in {esc(m.focus.label)} and "
            f"{self.unit_money(fine.total_per_unit)} fully loaded.</b> The marginal "
            f"cost of one more is {self.unit_money(fine.marginal_per_unit)}, since "
            f"only {esc(m.marginal_label or m.focus.label)} grows with volume."]
        if coarse is not fine:
            parts.append(
                f"The same period spread across {coarse.value:,.0f} "
                f"{esc(coarse.label)} is {self.unit_money(coarse.total_per_unit)} each, "
                f"{coarse.total_per_unit / fine.total_per_unit:,.0f} times the "
                f"cost of a {fine.label.rstrip('s')}. Of that "
                f"{self.unit_money(coarse.total_per_unit)}, "
                f"{self.unit_money(m.always_on.subtotal / coarse.value)} is always-on "
                f"capacity carried by every "
                f"{coarse.label.rstrip('s')} regardless of use.")
        return "".join(f"<p>{p}</p>" for p in parts)

    def _unit_charts(self) -> str:
        """One small bar chart per counter, comparing the three cost bases."""
        m = self.m
        if not m.units:
            return ""
        picks = [max(m.units, key=lambda u: u.value)]
        coarse = min(m.units, key=lambda u: u.value)
        if coarse is not picks[0]:
            picks.append(coarse)
        figs = []
        for u in picks:
            rows = [
                (esc(m.focus.label), u.focus_per_unit, "#f4511e", ""),
                ("Marginal", u.marginal_per_unit, "#f9ab00", ""),
                ("Fully loaded", u.total_per_unit, "#4285f4", ""),
            ]
            figs.append(
                f'<figure><h3>Cost per {esc(u.label.rstrip("s"))}</h3>'
                + charts.hbars(rows, m.symbol, 300, 24, 108, 96,
                               dp=4 if u.total_per_unit < 1 else 3)
                + f'<figcaption>Across {u.value:,.0f} {esc(u.label)} in the '
                  f'period.</figcaption></figure>')
        return f'<div class="block grid-2">{"".join(figs)}</div>'

    def page_forecast(self) -> str:
        m = self.m
        rows = [("Actual, period to date", m.subtotal, "#4285f4"),
                (f"Forecast, {m.period_end:%d %b}", m.forecast, "#f4511e"),
                ("Always-on floor, zero usage", m.always_on.projection, "#78909c")]
        if abs(m.flat_projection - m.forecast) > 0.01:
            rows.insert(2, ("Straight-line projection", m.flat_projection,
                            "#6b7280"))
        chart = ""
        if m.budget:
            bar_rows = [(l, v, c,
                         f"{self.money(v)} · {pct(v / m.budget.amount, 0)}")
                        for l, v, c in rows]
            chart = charts.budget_bars(
                bar_rows, m.budget.amount, m.budget.thresholds, m.symbol,
                m.budget.previous_amount if m.budget.changed_mid_period else None,
                600, 190)
        else:
            bar_rows = [(l, v, c, self.money(v)) for l, v, c in rows]
            chart = charts.hbars(bar_rows, m.symbol, 600, 30, 180, 124)

        basis = f"""<table>
  <caption>How each figure is built.</caption>
  <thead><tr><th class="l">Figure</th><th>Value</th><th class="l">Basis</th>
  </tr></thead>
  <tbody>
    <tr><td class="l">Actual, period to date</td><td>{self.money(m.subtotal)}</td>
      <td class="l">{m.days_elapsed} complete days of billed usage</td></tr>
    <tr><td class="l">Forecast, {m.period_end:%d %b}</td>
      <td><b>{self.money(m.forecast)}</b></td>
      <td class="l">{esc(cap(sanitize(m.forecast_source)))}, implying
        {self.rate(m.implied_remaining_per_day)} per day for the remaining
        {m.days_remaining} days</td></tr>
    <tr><td class="l">Straight-line projection</td>
      <td>{self.money(m.flat_projection)}</td>
      <td class="l">Period-to-date rate of {self.rate(m.per_day)} per day held
        flat to {m.period_end:%d %b}</td></tr>
    <tr><td class="l">Always-on floor</td>
      <td>{self.money(m.always_on.projection)}</td>
      <td class="l">The always-on services only, extended to
        {m.days_in_period} days</td></tr>
  </tbody></table>"""
        return f"""<h2>Forecast{" and budget" if m.budget else ""}</h2>
<p class="muted small">The period to date measured against what it is on track
  to close at{", and against the budget in force" if m.budget else ""}.</p>
<div class="block"><figure>{chart}
  <figcaption>{self._budget_caption()}</figcaption></figure></div>
<div class="block">{basis}</div>
{self._budget_block()}"""

    def _budget_caption(self) -> str:
        m = self.m
        if not m.budget:
            return "All figures in " + esc(m.currency) + "."
        b = m.budget
        prev = b.previous_amount if b.changed_mid_period else None
        drawn = [t for t in b.thresholds
                 if t < 1 and not (prev and abs(b.amount * t - prev) < 0.51)]
        parts = [f"Red line: the {esc(self.money(b.amount, 0))} budget."]
        if drawn:
            parts.append(
                "Dotted lines: its alert thresholds at "
                + ", ".join(f"{t * 100:.0f}%" for t in drawn)
                + f", that is {', '.join(esc(self.money(b.amount * t, 0)) for t in drawn)}.")
        if prev:
            parts.append(
                f"Dashed line: the previous {esc(self.money(prev, 0))} budget, in "
                f"force until {b.effective_from:%d %b}, which coincides with the "
                f"50% threshold of the current one.")
            parts.append(
                "The table below lists the thresholds that were actually reached, "
                "measured against the budget in force on each day.")
        return " ".join(parts)

    def _budget_block(self) -> str:
        m = self.m
        if not m.budget:
            return ""
        b = m.budget
        cards = f"""<div class="grid-3">
  <div class="stat"><div class="k">Actual vs budget</div>
    <div class="v">{pct(b.pct_actual, 0)}</div>
    <div class="n">{self.money(m.subtotal)} of
      {self.money(b.amount, 0)}</div></div>
  <div class="stat"><div class="k">Forecast vs budget</div>
    <div class="v">{pct(b.pct_forecast, 0)}</div>
    <div class="n">{self.money(m.forecast)} of
      {self.money(b.amount, 0)}</div></div>
  <div class="stat"><div class="k">Floor vs budget</div>
    <div class="v">{pct(b.pct_floor, 0)}</div>
    <div class="n">always-on capacity alone</div></div>
</div>"""
        cross = ""
        if b.crossings:
            rows = "".join(
                f'<tr><td class="l">{c.threshold * 100:.0f}% of '
                f'{self.money(c.budget_in_force, 0)}</td>'
                f'<td>{self.money(c.amount, 0)}</td>'
                f'<td class="l">{c.date:%d %b}</td>'
                f'<td>{self.money(c.cumulative)}</td></tr>'
                for c in b.crossings)
            cross = f"""<div class="block">
  <h3>Alert thresholds reached</h3>
  <table>
    <caption>Cumulative spend against the budget in force on each day.</caption>
    <thead><tr><th class="l">Threshold</th><th>Amount</th>
      <th class="l">Reached</th><th>Cumulative</th></tr></thead>
    <tbody>{rows}</tbody></table>
</div>"""
        return f'<div class="block">{cards}</div>{cross}'

    def page_basis(self) -> str:
        m = self.m
        notes = "".join(f"<li>{esc(sanitize(n))}</li>" for n in m.notes)
        svc = ", ".join(s.name for s in m.services if s.always_on) or "none"
        return f"""<h2>Basis of preparation</h2>
<p class="muted small">What the numbers are, and what they are not.</p>
<div class="block panel">
  <h3>Notes</h3>
  <ul class="small" style="margin:0; padding-left:5mm">{notes}</ul>
</div>
<div class="block">
<table>
  <thead><tr><th class="l">Item</th><th class="l">Definition</th></tr></thead>
  <tbody>
    <tr><td class="l">Period</td><td class="l">{m.period_start:%d %b %Y} to
      {m.period_end:%d %b %Y}, {m.days_in_period} days</td></tr>
    <tr><td class="l">Actual data</td><td class="l">{m.days_elapsed} complete
      days through {m.data_through:%d %b %Y}</td></tr>
    <tr><td class="l">Subtotal</td><td class="l">Cost after all savings, which is
      what the billing account is charged. List price was
      {self.money(m.list_total)}, savings {self.money(m.savings_total)},
      an effective {pct(m.discount_pct)} discount</td></tr>
    <tr><td class="l">Per day</td><td class="l">Subtotal divided by the
      {m.days_elapsed} complete days, not by the whole period</td></tr>
    <tr><td class="l">Projection</td><td class="l">Period-to-date rate held flat
      to the end of the period</td></tr>
    <tr><td class="l">Forecast</td><td class="l">{esc(cap(sanitize(m.forecast_source)))}</td></tr>
    <tr><td class="l">{esc(m.focus.label)}</td><td class="l">{self._focus_definition()}</td></tr>
    <tr><td class="l">Always-on</td><td class="l">{esc(svc)}</td></tr>
    <tr><td class="l">Complements</td><td class="l">Where the period is split in
      two, the second half is derived from the subtotal rather than summed from
      rounded rows, so the two halves always add to the total exactly</td></tr>
    <tr><td class="l">Rounding</td><td class="l">Values are rounded for display;
      totals come from the unrounded export, so a column may differ from its
      parts by one cent</td></tr>
    {self._extra_basis_rows()}
  </tbody>
</table>
</div>"""

    def _extra_basis_rows(self) -> str:
        m = self.m
        rows = []
        if m.budget:
            th = ", ".join(f"{t * 100:.0f}%" for t in m.budget.thresholds)
            if m.budget.changed_mid_period:
                held = (f'{self.money(m.budget.previous_amount, 0)} until '
                        f'{m.budget.effective_from:%d %b}, then '
                        f'{self.money(m.budget.amount, 0)}')
            else:
                held = f'{self.money(m.budget.amount, 0)} for the period'
            rows.append(
                f'<tr><td class="l">Budget</td><td class="l">{held}, with alerts '
                f'at {th}. Percentages elsewhere in this report use the current '
                f'{self.money(m.budget.amount, 0)}; the thresholds reached were '
                f'measured against the budget in force on each day</td></tr>')
        if m.daily:
            src = ("Reconstructed and rescaled to the exported subtotal"
                   if m.daily.estimated else "Taken from a daily export")
            rows.append(
                f'<tr><td class="l">Daily series</td><td class="l">{src}, '
                f'{len(m.daily.days)} days. Burst days are those above '
                f'{m.daily_stats.burst_factor:.2f} times the baseline</td></tr>'
                if m.daily_stats else
                f'<tr><td class="l">Daily series</td><td class="l">{src}</td></tr>')
        if m.units:
            names = ", ".join(u.label for u in m.units)
            rows.append(
                f'<tr><td class="l">Volumes</td><td class="l">{esc(cap(names))}'
                + (f", reported by {esc(m.unit_source)}" if m.unit_source else "")
                + (f" as of {esc(m.unit_as_of)}" if m.unit_as_of else "")
                + ". A volume that accumulates over the period is projected "
                  "forward; a headcount or a portfolio count is held flat"
                  "</td></tr>")
        rows.append(
            f'<tr><td class="l">Prepared</td><td class="l">'
            f'{m.generated_on:%d %b %Y}, from the billing export covering '
            f'{m.period_start:%d %b} to {m.data_through:%d %b %Y}</td></tr>')
        return "".join(rows)

    # ------------------------------------------------------------------ build
    def build(self) -> str:
        m = self.m
        candidates = [self.page_headline(), self.page_services(),
                      self.page_behaviour(), self.page_units(),
                      self.page_forecast(), self.page_basis()]
        self.pages = [p for p in candidates if p.strip()]
        total = len(self.pages)
        body = []
        for i, content in enumerate(self.pages, 1):
            body.append(
                f'<section class="page">{content}'
                f'<div class="foot"><span>{esc(sanitize(m.title))} · '
                f'{esc(m.period_label)}</span>'
                f'<span>{esc(m.entity)}</span>'
                f'<span>Page {i} of {total}</span></div></section>')
        title = f"{sanitize(m.title)} {m.period_label}"
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="generator" content="billing-exec-report">
<style>{CSS}</style>
</head>
<body>
{"".join(body)}
</body>
</html>
"""


def render(m: Model) -> tuple[str, int]:
    r = Report(m)
    html = r.build()
    return html, len(r.pages)
