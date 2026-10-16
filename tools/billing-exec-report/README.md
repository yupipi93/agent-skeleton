# billing-exec-report

Turns a Google Cloud Billing CSV export into an executive PDF report: one
self-contained HTML file with inline SVG charts, paginated for A4, rendered to PDF
through headless Chrome.

Python standard library only. The config is TOML (Python 3.11+) or JSON; YAML
also works when PyYAML happens to be installed, but nothing requires it. The PDF
needs a Chrome or Chromium binary. Nothing is asked at run time and nothing is
sent anywhere.

The `gcp` bundle's `gcp-billing-report` skill tells the agent how to collect the
inputs and check the result; this page is the tool's own reference.

## Try it

```bash
python3 tools/billing-exec-report/generate.py \
  --config tools/billing-exec-report/examples/sample/report.toml --pdf
```

```
html  .../examples/sample/report.html  (6 pages declared, 50 KB, self-contained)
pdf   .../examples/sample/report.pdf   (377 KB, 6 pages, pagination ok)
```

The sample is synthetic: invented services, figures and counters.

Options: `--out <path>` for the HTML, `--pdf [path]`, `--chrome <binary>`,
`--allow-pagination-drift` to downgrade a page-count mismatch to a warning.

Chrome lookup order: `--chrome`, `$CHROME_BIN`, `google-chrome`,
`google-chrome-stable`, `chromium`, `chromium-browser` or `chrome` on `PATH`, then
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` (and Chromium,
Canary, the same under `~/Applications`), then `/snap/bin/chromium`.

Exit codes: `0` ok, `2` bad usage or config, `3` figures do not reconcile (or an em
dash reached the output), `4` PDF page count does not match the document, `5` PDF
conversion failed.

## Adding a report

1. `mkdir -p tools/billing-exec-report/reports/<slug>` (the `reports/` folder is
   git-ignored, so real billing data never reaches the repository).
2. Export the billing view: console, Billing, Reports, group by **Service**, filter
   to the project or label, then **Download CSV**. Save it as `services.csv`.
3. Copy `examples/sample/report.toml` next to it and edit it. Every field is
   documented inline.
4. Run the command above with your config path.

The config carries what the export cannot know: the period, the last day with
complete data, the console's own forecast, which service to isolate, which
services bill around the clock, the budget, and any usage counters for unit
economics. Optional blocks are simply omitted and their pages disappear.

JSON configs use the same keys; dates are `"YYYY-MM-DD"` strings.

## What it produces

| Page | Content |
|---|---|
| 1 | Masthead, four KPI tiles, the verdict, a donut of the service mix, the focus service against everything else |
| 2 | Every service billed, with list, savings, subtotal, mix, per day, projection and both the reported and the per-day normalised change |
| 3 | Always-on against usage-driven cost, the daily trend with baseline and projected days, the daily distribution |
| 4 | Unit economics against the reported volumes, per counter, plus cost-per-unit charts |
| 5 | Forecast, how each figure is built, budget comparison and the alert thresholds reached |
| 6 | Basis of preparation: every definition and caveat |

Pages 3 and 4 appear only when the config provides a daily series and usage
counters.

## Design rules

Each rule exists because its absence produced a defect in a real report, and the
code enforces it.

**One source of truth.** `metrics.py` computes every figure once and `render.py`
does no arithmetic. A hand-built report once shipped a chart whose bar contradicted
a number in the surrounding text; a single model makes that impossible to express.

**Facts only, no proposals.** There is no field for a recommendation, an open
question or a next step. An executive cost report that argues with itself stops
being a reference. Analysis belongs in a separate document.

**No internal references.** No repo paths, ticket keys, PR links or hostnames.
`render.sanitize` warns on stderr when config text looks internal, because these
documents get forwarded outside the team.

**Budget changes are dated.** `budget.effective_from` and `previous_amount` are
first-class, and alert thresholds are evaluated against the budget in force on each
day. A report once measured every percentage against a budget that had been raised
hours earlier, which inverted its conclusion.

**Period-on-period percentages are normalised.** The console compares a partial
month against a whole previous month, which understates every change by nearly
half. The table shows the console's figure and the per-day normalised figure side by
side, and the notes explain the factor.

**Reconstructed data is labelled.** A daily series that did not come from an export
is rescaled to the exported subtotal and the document says so.

**No em dash.** The renderer replaces it and the build fails if one reaches the
output.

## Print correctness

The PDF is the deliverable, so the HTML is print-first: a light palette, one
`<section class="page">` per printed page, and `break-inside: avoid` on every card,
figure, table and row.

**Chrome scales the whole job to fit.** If any element is wider than the printable
area, Chrome shrinks the entire document instead of clipping it. The symptom is a
footer floating mid-page. The culprit is almost always a wide table: keep every
chart at or under 600 user units and let headers wrap.

**A fixed page height hides overflow.** With `height` plus `overflow: visible`, a
too-tall section prints over its own footer without adding a page, so a page-count
check passes on a visibly broken page. The page count is a regression gate, not a
layout check: look at the rendered pages.

The `docs` bundle's `docs-print-ready-pdf` skill covers these traps in general.

## Layout

```
generate.py          CLI, config loading, reconciliation, PDF conversion, pagination check
bexr/parse.py        CSV readers, tolerant of column order and currency
bexr/metrics.py      the canonical model: shares, rates, projections, cuts,
                     budget view, unit economics, and the notes
bexr/charts.py       inline SVG: donut, legend, split bar, hbars, daily columns,
                     budget bars, table sparkbars
bexr/render.py       print CSS and the page builders
examples/sample/     synthetic config plus export (tested by tests/test_gcp_billing_report.py)
reports/<slug>/      your real reports, git-ignored
```
