# Baseline features (ship them in release 1)

Each line was requested separately in two or more tools before it became a default.

## Identity and trust

- [ ] **Version in the page**: footer `<Tool> · release N · <short commit> · <date>`
      (plus "uncommitted changes" when the checkout is dirty), also in `/healthz`.
      `assets/build.py` reads it once at startup; `release` is a constant bumped with
      each numbered release of the backlog. A screenshot must say which build it shows.
- [ ] **Favicon set**: `favicon.svg` (dark rounded square, one gradient glyph in the
      accent, thick white strokes, readable at 16 px), `favicon-32.png`,
      `apple-touch-icon.png` (180 px), two `theme-color` metas, a manifest with
      `display: standalone`.
- [ ] **Live status pill**: live / offline / syncing, never a silent stale page. When
      the backend is unreachable, keep what is on screen and say so.

## Comfort

- [ ] **Theme switch**: system → light → dark chip, key `T`, stored per browser,
      applied before first paint (`assets/theme.js`), repaints canvases.
- [ ] **Language switch** when the audience is mixed: flag chip, `?lang=` override,
      stored per browser, English fallback (`assets/i18n.js`). Content stays as written.
- [ ] **Tooltips on every control**, saying what it does in its current state and its
      shortcut ("Pausar (espacio)").
- [ ] **Keyboard**: `/` search, `?` shortcuts sheet, `T` theme, `R` refresh or the
      tool's main toggle, `Esc` back or close; never while typing in a field.
- [ ] **Copy buttons** next to every id, link and command, with a visible "copied".
- [ ] **Relative times** ("hace 3 min") with the full date as tooltip, updated in
      place every minute; "ayer" is a calendar day.
- [ ] **Deep links** to one item (`/x/<id>`), and query entry points applied once and
      removed from the URL.

## Feedback

- [ ] Buttons react: pressed scale, a busy state (spinner, then ✓ or ✕) for anything
      that waits on the network, a toast with the result.
- [ ] Skeletons on first load, an empty state that says what will appear, an error
      state that is not the empty state.
- [ ] Confirmation for bulk or destructive actions as a second tap or a styled dialog,
      never `confirm()`.

## Phone and access

- [ ] Works at 360 and 390 px with no horizontal scroll; safe-area insets.
- [ ] Reachable from the phone when the user wants it (a tailnet-only proxy, a login
      allow-list), installable as a PWA.
- [ ] Focus ring on everything, 36 px targets (40 px on coarse pointers), `aria-pressed`
      on toggles, `aria-live` on status and lists, reduced motion honoured, 4.5:1 text.

## Server baseline

- [ ] Loopback bind, Host allow-list (421 otherwise), writes only as JSON POST/PATCH with
      a custom header, strict CSP, body size cap, always read the request body.
- [ ] A `version`/`boot` id in answers so the page drops responses older than its state.
- [ ] Service with `status` / `doctor` commands; interactive process priority.
