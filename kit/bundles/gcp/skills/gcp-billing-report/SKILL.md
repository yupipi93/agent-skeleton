---
name: gcp-billing-report
description: "Generate an executive Google Cloud cost report (HTML and A4 PDF) from a billing CSV export with tools/billing-exec-report. Use when billing data appears (CSV, console screenshot, service list) and the user wants a cost report, spend summary, AI vs infra split, unit economics or forecast."
---

# Executive cloud-cost reports

The generator is `tools/billing-exec-report/generate.py`. It reads a Google Cloud
Billing CSV export plus a declarative config (TOML or JSON) and writes a
self-contained HTML file with inline SVG charts, then a paginated PDF through headless
Chrome. It computes every figure once and cross-checks them, so a report never
contradicts itself. Load this skill as soon as billing data shows up, before writing
any cost analysis by hand.

```bash
python3 tools/billing-exec-report/generate.py \
  --config tools/billing-exec-report/reports/<slug>/report.toml --pdf
```

Try it on the synthetic sample first:
`python3 tools/billing-exec-report/generate.py --config tools/billing-exec-report/examples/sample/report.toml --pdf`.
The tool reference is `tools/billing-exec-report/README.md`; this skill covers what the
tool cannot decide for you.

## The output

| Page | Content | Needs |
|---|---|---|
| 1 | KPI tiles, the verdict, a donut of the service mix, the focus service against everything else | always |
| 2 | Every billed service: list, savings, subtotal, mix, per day, projection, reported and normalised change | always |
| 3 | Always-on against usage-driven cost, the daily trend, the daily distribution | a daily series |
| 4 | Unit economics per counter, cost-per-unit charts | usage counters |
| 5 | Forecast, how each figure is built, budget comparison, thresholds reached | always |
| 6 | Basis of preparation: every definition and caveat | always |

## Step 1: get a per-service export

The report needs **cost per service**, not a total. Ask in this order:

1. **Best: the CSV.** Console, Billing, Reports, group by **Service**, filter to the
   project or label, **Download CSV**. Save it as `services.csv` in
   `tools/billing-exec-report/reports/<slug>/` (git-ignored). The parser tolerates any
   column order, currency symbols, quoted thousands and a missing savings column.
2. **Acceptable: a screenshot or pasted table.** Transcribe it into a CSV with a header
   `Service description,Subtotal (<sym>)` plus `List cost` and `Negotiated savings`
   when visible. **Say that you transcribed it**: a transcription error is a wrong
   report.
3. **Not enough: a single total.** No breakdown, no focus cut, no always-on floor. Ask
   for the grouped export.

A daily export is optional (`input.daily_csv`). Without one you may reconstruct the
series from the console chart into the config's `daily` list; the tool rescales it to
the exported subtotal and labels day values as approximate. Never present a
reconstructed series as exported.

## Step 2: fill the config, deciding five things

Copy `tools/billing-exec-report/examples/sample/report.toml` (commented field by field)
into the report folder.

**`data_through`: the last day with complete data.** Usually yesterday; on the console
daily chart, the last coloured bar before the grey ones. Every per-day figure divides
by it. "This month" on the 17th means `data_through` is the 16th.

**`budget`: read it from the live source, never assume.** Where it is defined right
now: the IaC on a fresh checkout of the default branch, or
`gcloud billing budgets list --billing-account=<id>`. A report once measured every
percentage against a budget raised hours earlier on an unpulled branch, and its
conclusion inverted. When the budget changed in the period, set `previous_amount` and
`effective_from` so thresholds are evaluated per day.

**`forecast.value`: the console's own number, or nothing.** Pass it verbatim with a
source label; the report also shows the straight-line projection beside it. Without
a console figure, omit the table and the tool projects the period-to-date rate. Never
invent a forecast or print a range next to an official figure.

**`focus`: the one service the report is built around.** Whatever question was
asked: "how much of this is AI?" makes `Vertex AI` the focus. Several services can
share one label via `focus.services`.

**`always_on`: what bills whether the product is used or not.** Test: would this
line still bill if nobody touched the product for a week?

| Always-on | Usage-driven |
|---|---|
| Cloud SQL (unless stopped off-hours) | Vertex AI and other model inference |
| Memorystore, Filestore, persistent disks | Cloud Run and Functions at `min_instances: 0` |
| Networking: forwarding rules, Cloud NAT, static IPs | BigQuery on-demand queries |
| Secret Manager, KMS, Artifact Registry, Cloud DNS | Cloud Build, Cloud Tasks, Pub/Sub, Scheduler |
| Compute Engine instances that are not stopped | Egress that tracks traffic |
| Cloud Storage capacity | Cloud Storage operations |

Cloud Run with `min_instances >= 1` is always-on for the reserved instances: check the
service config rather than guessing.

## Step 3: run it and read the exit code

| Code | Meaning | Do |
|---|---|---|
| 0 | ok | Step 4 |
| 2 | bad usage or config | Fix the config |
| 3 | figures do not reconcile with the export, or an em dash reached the output | **Stop, do not retry**: the export was misread or the config is wrong |
| 4 | PDF page count differs from the declared count | A section overflows: fix the too-tall or too-wide element; never pass `--allow-pagination-drift` to hide it |
| 5 | PDF conversion failed or no Chrome found | Install Chrome or pass `--chrome` / `CHROME_BIN` |

## Step 4: verify before delivering

The gates catch regressions, not a document that looks wrong. **Look at the rendered
pages** (screenshot the HTML or render PDF pages to images) and, for an executive
audience, have a **different agent** review a frozen copy. Check, in order:

1. The same quantity never appears with two printed values, charts included.
2. Percentages shown as shares of one total sum to 100%.
3. No box is clipped, no line crosses a label, footers sit at the page bottom.
4. No proposals, open questions or internal references (below).
5. Contrast survives printing: no white on mid-tone fills, grey text at least 4.5:1.

## What an executive cost report must not contain

- **Recommendations, proposals or next steps.** A cost report is a reference; analysis
  and options belong in a separate document.
- **Open questions or pending items.** State an assumption as a fact of the
  preparation, or leave it out.
- **Internal references**: repo paths, settings files, Terraform, PR or ticket links,
  hostnames, IPs, raw project ids. Use a plain-language `report.entity`. The renderer
  warns on stderr when text looks internal.
- **Em dashes**: the build fails on one.

## Reading the change column honestly

The console compares the selected period with the whole previous period. For a
month-to-date view that is 16 days against 31, so every reported change is misleading,
and not in the direction you would guess: a service reporting no change is spending
nearly twice as much per day. The table prints the reported and the per-day
normalised change; quote the normalised one in prose and say so.

## Related

- `docs-print-ready-pdf`: the print and pagination traps behind the layout.
- `docs-markdown-pdf-vscode`: Markdown to PDF for documents not built by this tool.
