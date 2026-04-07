# CEQ Brand Color Guide

This document records intentional color deviations between the CEQ brand palette and the colors used in terminal output, UI surfaces, and dark-theme interfaces. Every deviation listed here is a deliberate design decision, not a bug.

## Color Deviation Table

| Role | Brand Hex | Implementation Hex | Delta | Direction |
|------|-----------|-------------------|-------|-----------|
| Primary green | `#2c8136` | `#16a34a` | +18% lightness, +12% saturation | Brighter, more vivid |
| Primary violet | `#58326f` | `#cc66ff` | +38% lightness, +40% saturation | Significantly lighter |

## Why the Deviations Exist

### Terminal Green: `#16a34a` vs Brand `#2c8136`

The brand green (`#2c8136`) was designed for print and light-background marketing collateral. When rendered as terminal text on a dark background (typically `#0d1117` or `#1e1e1e`), it falls below the WCAG AA contrast ratio of 4.5:1. The terminal variant (`#16a34a`) was selected to solve three problems simultaneously:

1. **Contrast compliance.** `#16a34a` on a `#0d1117` background yields a contrast ratio of approximately 5.8:1, comfortably above the AA threshold. The brand green produces roughly 3.4:1 in the same context.
2. **Readability at small sizes.** Terminal text is typically rendered at 12-14px in a monospaced font. At that size, reduced contrast causes eye strain during extended sessions. The brighter green preserves legibility across long log outputs and CLI feedback.
3. **Dark theme harmony.** Modern developer tools default to dark themes. The adjusted green sits naturally alongside Tailwind's `green-600` scale, avoiding the muddy appearance that the brand green produces against dark grays.

### Neon Violet: `#cc66ff` vs Brand `#58326f`

The brand violet (`#58326f`) serves as a secondary accent in brand guidelines, intended for subtle backgrounds and muted highlights. In UI contexts the deviation is more dramatic because the use case is fundamentally different:

1. **UI contrast on dark surfaces.** The brand violet against a dark card (`#1a1a2e` or similar) produces a contrast ratio below 2:1, making it invisible as a border, badge, or interactive indicator. `#cc66ff` achieves approximately 6.2:1 against the same surface.
2. **Action affordance.** Interactive elements (buttons, links, focus rings) need to read as tappable or clickable. A muted purple fails to communicate interactivity. The neon variant provides the visual weight necessary to signal "this is actionable" without resorting to an entirely different hue.
3. **Dark theme optimization.** Desaturated violets collapse into gray on OLED and high-contrast displays. The neon variant retains its hue identity across a wide range of display calibrations, ensuring the violet always reads as purple rather than charcoal.

## Usage Contexts

### Brand Colors (Use These For)

| Color | Hex | Contexts |
|-------|-----|----------|
| Brand green | `#2c8136` | Print materials, light-background web pages, logos on white, marketing PDFs |
| Brand violet | `#58326f` | Print accents, light-theme subtle backgrounds, brand guideline documents |

### Implementation Colors (Use These For)

| Color | Hex | Contexts |
|-------|-----|----------|
| Terminal green | `#16a34a` | CLI output, terminal status messages, dark-theme success indicators, code editor highlights |
| Neon violet | `#cc66ff` | Dark-theme interactive elements, focus rings, badges, links on dark surfaces, accent borders, selected states |

## Accessibility Notes

All implementation colors were validated against WCAG 2.1 AA requirements in their intended contexts:

- **Terminal green on dark backgrounds:** 5.8:1 minimum (AA for normal text: 4.5:1)
- **Neon violet on dark backgrounds:** 6.2:1 minimum (AA for normal text: 4.5:1)
- **Brand green on light backgrounds:** 4.6:1 minimum (AA compliant in its intended context)
- **Brand violet on light backgrounds:** 7.1:1 minimum (AAA compliant in its intended context)

The deviations ensure that both the brand palette and the implementation palette meet accessibility standards in their respective environments.

## When to Use Which

Use the **brand colors** when the background is light (white, off-white, light gray) and the medium is static (print, PDF, slide decks, marketing pages).

Use the **implementation colors** when the background is dark (terminal, dark-theme UI, code editors) and the element must be readable, interactive, or visible at small sizes.

If you are adding a new surface or component and are unsure which variant to use, check the background luminance. If the background has a relative luminance below 0.2, use the implementation color. If above 0.2, use the brand color.
