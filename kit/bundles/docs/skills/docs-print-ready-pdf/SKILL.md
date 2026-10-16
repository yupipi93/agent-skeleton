---
name: docs-print-ready-pdf
description: "Build HTML that converts cleanly to a paginated PDF with headless Chrome (macOS, Linux): page breaks, footers on the page edge, print-safe colour, page-count check. Use for any HTML meant as a PDF (reports, one-pagers, invoices), or a PDF with a floating footer, clipped content or no backgrounds."
---

# Print-ready HTML to PDF

Screen HTML and print HTML are different documents. Load this before writing the first
line of CSS for something destined for print: two of the failure modes below are
invisible in the browser and point nowhere near their cause.

## Converting

`kit/bundles/docs/scripts/chrome.sh` finds Chrome and converts with a throwaway
profile:

```bash
kit/bundles/docs/scripts/chrome.sh path                         # which binary it will use
kit/bundles/docs/scripts/chrome.sh pdf report.html report.pdf
kit/bundles/docs/scripts/chrome.sh screenshot report.html page.png 1080,1500
```

Lookup order: `$CHROME_BIN`, then `google-chrome`, `google-chrome-stable`, `chromium`,
`chromium-browser`, `chrome` on `PATH` (Linux), then
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` (macOS installs Chrome
as an app bundle, never on `PATH`), Chromium and Canary, the same under
`~/Applications`, then `/snap/bin/chromium`.

The raw command, if you need other flags:

```bash
CHROME="$(kit/bundles/docs/scripts/chrome.sh path)"
"$CHROME" --headless=new --disable-gpu --no-first-run \
  --user-data-dir="$(mktemp -d)" --no-pdf-header-footer \
  --run-all-compositor-stages-before-draw --virtual-time-budget=6000 \
  --print-to-pdf=out.pdf "file://$PWD/in.html"
```

`--no-pdf-header-footer` removes Chrome's own header and footer (URL and date printed
over your layout). Snap-packaged Chromium on Linux has a private `/tmp` and cannot read
files you wrote there: render from a folder under `$HOME`.

## The two traps that waste an afternoon

### Chrome silently scales the whole job to fit

If **any** element is wider than the printable area, headless Chrome neither clips nor
overflows: it shrinks **the entire document** until the widest element fits.
Symptoms point nowhere near the cause:

- footers land at 80% of the page height instead of the bottom;
- everything looks slightly clipped at the right edge;
- `min-height` and `height` in mm seem ignored.

The usual culprit is a wide table: `white-space: nowrap` on the headers of a
ten-column table is enough. Diagnose it by checking whether a footer that should sit
at the bottom is high by a constant ratio: that ratio is the scale factor. Prevent it:
let headers wrap, keep charts at or under 600 user units for A4 portrait with 12 mm
margins, never `nowrap` a header row.

### A fixed page height hides overflow from the page-count check

With `height` plus `overflow: visible`, a section taller than its box prints **over
its own footer** without adding a page, so a page-count check passes on a visibly
broken page. Use `height` only when you also look at the pages; use `min-height` if
overflow must be detected automatically (the section grows, breaks, and the page
count changes).

## Page structure

One section per printed page; write the footer at render time:

```html
<section class="page">
  ...content...
  <div class="foot"><span>Title</span><span>Page 1 of 6</span></div>
</section>
```

The footer text is only right if no section overflows, which the page-count check
verifies.

## The CSS that matters

```css
@page { size: A4 portrait; margin: 13mm 12mm 12mm 12mm; }

html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

@media print {
  .page {
    page-break-after: always; break-after: page;
    height: 270mm;              /* 297 - 13 - 12, minus 2mm of slack */
    padding: 0 1mm 13mm 0;      /* the 1mm keeps right borders on the page */
    margin: 0; max-width: none;
  }
  .page:last-of-type { page-break-after: auto; break-after: auto; }

  .card, .stat, figure, table, blockquote { page-break-inside: avoid; break-inside: avoid; }
  tr, thead { page-break-inside: avoid; break-inside: avoid; }
  thead { display: table-header-group; }   /* repeat headers if a table spans pages */
  h1, h2, h3 { page-break-after: avoid; break-after: avoid; }
}

@media screen {                  /* a page-like preview while authoring */
  body { background: #eceff3; padding: 8mm 4mm; }
  .page { background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.16);
          min-height: 262mm; padding: 10mm; }
}
```

Easy to miss:

- **`padding-right: 1mm` on the page.** A box flush with the printable edge loses its
  right border: the stroke falls outside the page.
- **`minmax(0, 1fr)`, never `1fr`, in grid columns.** `1fr` floors at the item's
  min-content width, so a four-card grid overflows and the last card is clipped.
- **Reserve height for wrapping labels.** Give KPI label slots a `min-height` of two
  lines so one wrapping label does not break the baseline of the row.

## Colour and contrast

`--print-to-pdf` honours backgrounds when `print-color-adjust: exact` is set. Still
design print-first:

- **Light background, dark ink.** A dark theme wastes ink and fails first on a printer.
- **4.5:1 minimum for body and numeric text**, 3:1 for graphical marks. `#80868b` on
  white is 3.68:1 and fails; `#5f6368` is 6.14:1 and passes.
- **Never white text on a mid-tone fill** (white on mid orange is about 3.5:1): put
  the label on an opaque plate with dark ink.
- **Define contrast tokens once.** Low-contrast defects recur where a second call site
  reuses a token that was fixed at only one place.

## Labels, lines and occlusion

- An opaque plate behind a label stops a line striking through the text, but it
  **breaks the line**, a defect if that line is the primary reference.
- **Move the label, do not break the important line**: place it where no primary line
  passes (often at the start of a bar), and let plates occlude only gridlines.
- Apply it to labels on **both** sides of a bar.

## Charts

Inline SVG, not raster: sharp at any scale and self-contained. Give every SVG a
`viewBox` and size it with CSS `width: 100%; height: auto`. Axis steps that read as
money or counts: 1, 1.5, 2, 2.5, 3, 4, 5, 7.5 and 10 times a power of ten, five or six
intervals. Too few candidates produce axes labelled 75, 150, 225.

## Verifying

Compare the PDF's page count with the number of sections the document declares (no
library needed):

```python
import re
data = open("out.pdf", "rb").read()
counts = [int(m.group(1)) for m in
          re.finditer(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data, re.S)]
pages = max(counts) if counts else len(re.findall(rb"/Type\s*/Page(?![sA-Za-z])", data))
```

A mismatch means a section overflowed: fail the build. Then **look at the pages**
(`chrome.sh screenshot`, or render PDF pages with `pdftoppm` from poppler when it is
installed), and for anything with an audience have a different agent review a frozen
copy. The page count cannot see a clipped border, a struck-through label or a footer
floating mid-page.

## Related

- `gcp-billing-report`: a generator built on all of the above
  (`tools/billing-exec-report`).
- `docs-markdown-pdf-vscode`: the Markdown route, when you are not writing the HTML.
