/**
 * MADFAM brand constants.
 *
 * These values act as the local source of truth until @madfam/core is
 * published as an installable package.  When that happens, replace this
 * file with a re-export:
 *
 *   export { brand } from "@madfam/core";
 *
 * Every color is provided in three representations so consumers can
 * pick whichever fits their context:
 *   - hex   – raw hex string (canvas, SVG, emails)
 *   - hsl   – CSS hsl() string (inline styles)
 *   - hsla  – hue / saturation / lightness triple for Tailwind's
 *             hsl(var(--x)) pattern (no wrapper, no alpha)
 */

// ---------------------------------------------------------------------------
// Color types
// ---------------------------------------------------------------------------

export interface BrandColor {
  /** e.g. "#16a34a" */
  hex: string;
  /** e.g. "hsl(142, 76%, 36%)" */
  hsl: string;
  /** Raw "H S% L%" triple for CSS custom properties (Tailwind-compatible) */
  hslRaw: string;
}

export interface BrandPalette {
  /** Terminal variants — high-saturation, screen-glow feel */
  terminal: {
    green: BrandColor;
    violet: BrandColor;
  };
  /** Brand variants — print-safe, slightly muted */
  brand: {
    green: BrandColor;
    violet: BrandColor;
  };
}

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------

export const brand: BrandPalette = {
  terminal: {
    green: {
      hex: "#16a34a",
      hsl: "hsl(142, 76%, 36%)",
      hslRaw: "142 76% 36%",
    },
    violet: {
      hex: "#cc66ff",
      hsl: "hsl(280, 100%, 70%)",
      hslRaw: "280 100% 70%",
    },
  },
  brand: {
    green: {
      hex: "#2c8136",
      hsl: "hsl(127, 49%, 34%)",
      hslRaw: "127 49% 34%",
    },
    violet: {
      hex: "#58326f",
      hsl: "hsl(277, 38%, 32%)",
      hslRaw: "277 38% 32%",
    },
  },
} as const;

// ---------------------------------------------------------------------------
// CSS custom property names (matches globals.css declarations)
// ---------------------------------------------------------------------------

export const brandCssVars = {
  terminalGreen: "--color-terminal-green",
  brandGreen: "--color-brand-green",
  terminalViolet: "--color-neon-violet",
  brandViolet: "--color-brand-violet",
} as const;
