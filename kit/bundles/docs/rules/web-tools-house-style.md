---
description: Every web tool, panel or dashboard you create or redesign starts from the house style starter and ships its baseline features (version shown, theme switch, favicon, phone layout).
apply: always
---

# Web tools start from the house style

When you create a web tool, panel, dashboard or single-page HTML app, or redesign one,
load the skill `web-tool-house-style` before writing markup and start from its
`assets/` (tokens, theme, i18n, build footer, favicon recipe, screenshot script).

- Keep the shared neutrals; give the tool only its own accent colour.
- Ship the baseline in `references/defaults.md` from the first release: version in the
  page, theme switch, favicon set, tooltips, keyboard (`/`, `?`, `T`, `Esc`), live status,
  phone layout without horizontal scroll, focus rings and reduced motion.
- Before reporting, take desktop and phone shots in light and dark with
  `assets/shoot.mjs` and look at them.

A user's own overlay can add the tools to copy from and personal defaults (language,
where tools are registered).
