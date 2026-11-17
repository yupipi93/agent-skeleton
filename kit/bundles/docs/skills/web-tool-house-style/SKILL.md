---
name: web-tool-house-style
description: "House style and default features for local web tools and dashboards: tokens, glass cards, nebula, chips, theme and language switch, version footer, favicon, shortcuts, a11y. Use when creating or redesigning any web tool, panel or dashboard."
---

# Web tool house style

Every small web tool (a local panel, a dashboard, a launcher card) starts from the same
look and the same baseline features, so tools feel like one family and the requests a
user repeats for every tool (theme switch, visible version, tooltips, phone layout) are
already there. Start from the files in `assets/`; do not restyle from scratch.

## When to use

- Creating a new web tool, panel, dashboard or single-page HTML app.
- Redesigning or "moving to the common style" an existing one.
- A review finds a tool missing the baseline (no version shown, no theme switch, no
  favicon, hover-only controls, horizontal scroll on a phone).

## Steps

1. **Copy the starter** into the tool's static folder and link it:
   `assets/house.css` (tokens + components), `assets/theme.js` (in `<head>`, before the
   CSS: no theme flash), `assets/i18n.js` when the UI has more than one language,
   `assets/build.py` (or its logic) for the version footer, `assets/shoot.mjs` for
   screenshots, `assets/favicon.svg` as the icon template.
2. **Pick the tool's own colour** and set only `--accent`, `--accent-ink`,
   `--accent-soft` and the three `--nebula-*` tints, in light and both dark blocks. Keep
   the neutrals: they are what makes the family. Check 4.5:1 for accent text on `--bg`
   and on `--accent-soft`.
3. **Lay out the page** with the shared skeleton (`references/layout.md`): sticky
   frosted top bar (brand mark + lowercase name + status pill left; search; primary
   pill; round chips for language, theme, `?`), a filter row of segmented controls and
   chips, glass cards, a footer with the version.
4. **Ship the baseline features** in `references/defaults.md`. They are not optional
   extras: each one was asked for in more than one tool.
5. **Avoid the known pitfalls** in `references/pitfalls.md` (stale answers painting over
   new ones, scroll jumps on refresh, focus loss, clipped focus rings, phone overflow).
6. **Verify**: `node assets/shoot.mjs <outdir> <url>` gives desktop and phone shots in
   light and dark and flags horizontal overflow; look at every shot. Check the 32 px
   favicon. Run the tool's tests.

## Gotchas

- `overflow-x: clip` on the page column also clips a full-bleed header band: put it on
  `body`.
- Headless `chrome --screenshot` never returns on a page with an open EventSource or
  long poll; use `assets/shoot.mjs` (CDP, device emulation, cleans up Chrome on every
  exit path).
- `backdrop-filter` on an ancestor makes it the containing block of `position: fixed`
  children: keep popovers out of blurred containers.
- Do not encode the theme only in the media query: the manual choice
  (`data-theme`) must win in both directions, so dark values live in two blocks.
- Reduced motion: stop the nebula, pulses, shimmer and canvas physics, in CSS and JS.

## References

- `references/tokens.md`: palette, type scale, radii, shadows, motion, with the why.
- `references/layout.md`: page skeleton and where each kind of control goes.
- `references/defaults.md`: the baseline feature checklist.
- `references/pitfalls.md`: bugs that recurred across tools and their default fix.
- `assets/`: the starter files.
