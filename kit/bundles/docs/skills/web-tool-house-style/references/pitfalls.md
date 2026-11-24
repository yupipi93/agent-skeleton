# Pitfalls that kept coming back

Audits of several tools found the same bugs again and again. Build these fixes in from
the start.

| Pitfall | Default fix |
|---|---|
| A slow response paints over a newer one (two quick filter changes) | A request counter per view; drop answers older than the last request or write |
| A server restart double-counts or freezes the page | A boot id plus a data version in every answer |
| A live refresh moves the scroll | Anchor on the first visible item and restore its offset; keep pages already loaded; per-tab anchor in `sessionStorage` |
| Focus lost when a list re-renders | Re-render only when the signature changes; restore focus by id with `preventScroll` |
| Handlers stacked on every render (a toggle fires twice) | Bind once, delegate from a stable parent, or assign `onclick` |
| Space or Enter fires twice on a focused button | Only a Tab-focused button takes Space; cancel the keyup of a Space the page used |
| Focus ring clipped | No `overflow: hidden` around controls; offset rings |
| Touch targets too small | 36 px minimum, 40 px on `(pointer: coarse)`, split pairs get one each |
| Horizontal overflow on a phone | Wrap long tokens, ellipsis with the full text as tooltip, test 360 / 390 px |
| Hover styles stick after a tap | Hover only inside `@media (hover: hover)` |
| Theme switch leaves stale colours | Re-read CSS variables and repaint canvases on change |
| Reduced-motion overrides ignored | Put them last in the stylesheet; mirror in JS |
| Wrong day near midnight or across DST | One configured time zone; calendar-day arithmetic |
| A failing source reads as "nothing to do" | Unknown is not empty: show stale or failed explicitly |
| A query parameter comes back on reload or Back | Apply once, then `history.replaceState` |
| Background service throttled by the OS | Interactive or standard process priority, idle back-off |
| Unread request body breaks keep-alive | Always drain the body; validate `Content-Length` |
| An idle page holds the GPU at 50-100 % (an animated background under `backdrop-filter` glass re-blurs every panel 60 times a second; worse on a 5K screen) | `data-ambient` + `assets/ambient.js` on slow drifts, `data-ambient="live"` on pulses; glass only where content passes beneath; infinite animations on `transform`/`opacity` only; canvas loops idle when nothing moves. Measure Chrome's GPU process with the page open, not just the look |
| Untrusted text in `innerHTML` | Escape every interpolated value; allow-list inline markup |
