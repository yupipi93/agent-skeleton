# Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ● name  [status]        [ 🔍 search ............ / ]  [▶ Primary N] ◐ 🇪🇸 ? │  sticky, frosted, full-bleed band
├──────────────────────────────────────────────────────────────────────────┤
│ (Todas|Sin leer|Destacadas)  ● chip  ● chip  [picker ▾]  [select]   action │  filter row; one scrolling row on a phone
├───────────────────────────────┬──────────────────────────────────────────┤
│ EYEBROW                       │  detail / sheet                           │
│ 42  thin hero number · context│  title 24px · meta tags                   │
│ ── cards (translucent, 18px) ──     │  📌 what needs you (accent box with edge) │
│                               │  main content                             │
│ tool · release N · abc1234    │  primary actions …………… quiet actions      │
└───────────────────────────────┴──────────────────────────────────────────┘
```

Where things go:

- **Left of the bar**: brand mark (a small animated glyph in the accent), the lowercase
  name, and one status pill (live, offline, syncing). The brand links home.
- **Right of the bar**: at most one primary pill (ink background), then round 36 px
  chips: language (flag of the current language), theme (◐ ☀ ☾), help `?`. On a phone
  the search drops to its own row and the primary keeps only its icon and count.
- **Filters**: mutually exclusive options are one segmented control (ink-inverted
  selection), independent toggles are chips with `aria-pressed`, long lists are a
  searchable popover. A filter row never wraps to three lines on a phone: it scrolls.
- **Hero**: the one number the tool exists for (pending, cost, tickets waiting), thin
  and big, with one line of context.
- **Cards**: translucent (no backdrop blur over the nebula), the item's state as an accent edge or dot, controls on the right,
  48 px-ish targets on touch screens.
- **"What needs you" first**: anything the user must act on sits above the content, in
  an accent-soft box with an eyebrow label.
- **Actions**: primary actions first; destructive or rare ones (archive, download,
  regenerate) quieter and to the right.
- **Footer**: `<Tool> · release N · <commit> · <date>` in `--faint`.
- **Desktop at 960 px and up**: list and detail side by side, the detail sticky. Below,
  one column; the detail replaces the list and the back arrow lives in the top bar.
