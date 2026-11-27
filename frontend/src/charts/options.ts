import type { ChartOptions, ChartType } from 'chart.js'
import { formatInteger } from '../utils/format'
import type { ChartTheme } from './theme'

interface BaseOptions {
  /** Show the legend; required whenever a chart has two or more series. */
  legend?: boolean
  horizontal?: boolean
  yTitle?: string
  integerTicks?: boolean
  /** Start the value axis at zero (default). Disable for slow-moving totals like stars. */
  beginAtZero?: boolean
}

/**
 * Shared options: hairline recessive grid, no dashed rules, a crosshair-style index tooltip
 * and legend for multi-series charts. Bar and line charts reuse the same scale settings.
 */
export function baseOptions<T extends ChartType>(
  theme: ChartTheme,
  {
    legend = false,
    horizontal = false,
    yTitle,
    integerTicks = true,
    beginAtZero = true,
  }: BaseOptions = {},
): ChartOptions<T> {
  const valueAxis = {
    beginAtZero,
    grid: { color: theme.grid, drawTicks: false },
    border: { display: false },
    ticks: {
      color: theme.textSecondary,
      padding: 8,
      precision: integerTicks ? 0 : undefined,
      callback: (value: string | number) => formatInteger(Number(value)),
    },
    title: yTitle
      ? { display: true, text: yTitle, color: theme.textSecondary, font: { size: 11 } }
      : undefined,
  }
  const categoryAxis = {
    grid: { display: false },
    border: { color: theme.axis },
    ticks: { color: theme.textSecondary, maxRotation: 0, autoSkipPadding: 12 },
  }

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 250 },
    indexAxis: horizontal ? 'y' : 'x',
    interaction: { mode: 'index', intersect: false, axis: horizontal ? 'y' : 'x' },
    plugins: {
      legend: {
        display: legend,
        position: 'top',
        align: 'end',
        labels: {
          color: theme.textSecondary,
          usePointStyle: true,
          pointStyle: 'rectRounded',
          boxWidth: 8,
          boxHeight: 8,
          padding: 14,
          // Keep legend entries in dataset order; `order` is used only for drawing.
          sort: (a, b) => (a.datasetIndex ?? 0) - (b.datasetIndex ?? 0),
        },
      },
      tooltip: {
        backgroundColor: theme.surface,
        titleColor: theme.text,
        bodyColor: theme.text,
        borderColor: theme.axis,
        borderWidth: 1,
        padding: 10,
        boxPadding: 4,
        usePointStyle: true,
      },
    },
    scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
  } as ChartOptions<T>
}

/** Bar marks: thin, rounded data end anchored to the baseline, 2px gap between bars. */
export const barStyle = {
  borderRadius: 4,
  borderSkipped: 'start' as const,
  categoryPercentage: 0.85,
  barPercentage: 0.9,
  maxBarThickness: 28,
}

export const lineStyle = {
  borderWidth: 2,
  pointRadius: 0,
  pointHoverRadius: 4,
  pointHitRadius: 12,
  // Monotone interpolation never overshoots below zero or invents peaks between points.
  cubicInterpolationMode: 'monotone' as const,
}
