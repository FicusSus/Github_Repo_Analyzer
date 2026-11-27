import type { Theme } from '../composables/useTheme'

/**
 * Chart colors come from CSS custom properties (src/styles.css) so the light and dark palettes
 * are defined in one place. The categorical order was validated for colour-vision deficiency
 * in both modes; slots are assigned in fixed order and never cycled.
 */
export interface ChartTheme {
  series: string[]
  other: string
  text: string
  textSecondary: string
  grid: string
  axis: string
  surface: string
}

const SERIES_SLOTS = 8

function cssVar(styles: CSSStyleDeclaration, name: string, fallback: string): string {
  return styles.getPropertyValue(name).trim() || fallback
}

// `theme` is a parameter so callers' computed() values re-evaluate when it changes.
export function readChartTheme(_theme: Theme): ChartTheme {
  const styles = getComputedStyle(document.documentElement)
  return {
    series: Array.from({ length: SERIES_SLOTS }, (_, i) =>
      cssVar(styles, `--series-${i + 1}`, '#338ced'),
    ),
    other: cssVar(styles, '--series-other', '#8a8a8a'),
    text: cssVar(styles, '--text-primary', '#efefef'),
    textSecondary: cssVar(styles, '--text-secondary', '#9c9c9c'),
    grid: cssVar(styles, '--grid', '#303030'),
    axis: cssVar(styles, '--axis', '#474747'),
    surface: cssVar(styles, '--surface-1', '#191919'),
  }
}

export function seriesColor(theme: ChartTheme, slot: number | null): string {
  if (slot === null) return theme.other
  return theme.series[(slot - 1) % theme.series.length] ?? theme.other
}

/** Translucent variant of a hex colour for area fills. */
export function withAlpha(hex: string, alpha: number): string {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex)
  if (!match?.[1]) return hex
  const value = parseInt(match[1], 16)
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}
