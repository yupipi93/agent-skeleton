# Tokens

All values live in `assets/house.css`. This file says what each group is for.

## Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` / `--bg-2` | `#f4f1ea` / `#ebe6db` | `#07080c` / `#0d0f15` | Warm paper by day, deep night by dark |
| `--ink` | `#15161a` | `#eef0f4` | Text, and the background of a selected segment |
| `--muted` / `--faint` | `#5d6068` / `#75787f` | `#a0a6b1` / `#858b96` | Secondary text; `--faint` still passes 4.5:1 |
| `--line`, `--card-line` | ink at 10 % / 8 % | ink at 9 % / 8 % | Hairlines |
| `--card` | `rgba(255,255,255,.74)` | `rgba(16,18,25,.66)` | Translucent glass, always with `backdrop-filter` |
| `--card-solid` | `#fbf9f4` | `#10121a` | Popovers, dialogs, inputs over glass |
| `--accent*` | per tool | per tool | The tool's own colour: brand mark, primary state, unread edge |
| `--ok`, `--warn`, `--bad`, `--info` + `-soft` | `#17703d`, `#7d5600`, `#b42232`, `#2458c2` | `#3fcf8e`, `#e9b949`, `#ff6b6b`, `#7aa7ff` | One meaning each; text keeps 4.5:1 on its soft tint |
| `--focus` | `#2f6fe4` | `#7aa7ff` | The focus ring, everywhere |
| `--nebula-a/b/c` | 7-10 % tints | 9-16 % tints | The drifting background glow |
| `--glow` | `.55` | `1` | Multiplier for halos, so dark mode glows and light mode stays calm |

Accent colours already taken in the family (pick another for a new tool): pink-red
`#d61f4b`, amber `#e98a00`, blue `#2a78d6`, coral `#c2410c`.

## Type

- System stack, `15px/1.45`, antialiased. No web fonts (strict CSP, offline use).
- Brand name lowercase, `650`, `17px`, `letter-spacing: .02em`.
- Eyebrow labels: `12px`, `600`, `letter-spacing: .14em`, uppercase, `--muted`.
- Hero numbers: weight `200`, `clamp(44px, 6vw, 72px)`, `tabular-nums`.
- Every number in a UI uses `font-variant-numeric: tabular-nums`.
- Monospace (`ui-monospace, SFMono-Regular, Menlo`) only for keys, ids and code.

## Shape and depth

- Radius: cards `18px`; rows, inputs, popover items `10-12px`; tags `6-7px`; pills and
  chips `999px`.
- Shadow: `0 1px 2px` plus a long soft `0 12px 32px` (light) / `0 16px 40px` (dark).
- State edge on a card: `box-shadow: inset 3px 0 0 var(--accent)` (unread, your turn).

## Motion

- House curve `cubic-bezier(.2, .8, .2, 1)`; slide-ins `cubic-bezier(.16, 1, .3, 1)`.
- Press: `transform: scale(.95)` over `.12s`. Hover: `filter: var(--hover)`
  (`brightness(.96)` light, `1.15` dark).
- Living details: the brand mark pulses or breathes; the nebula drifts over 48 s.
- `prefers-reduced-motion: reduce` stops all of it.
