<script setup lang="ts">
import type { ChartData } from 'chart.js'
import { computed, watch } from 'vue'
import { Line } from 'vue-chartjs'
import { api } from '../api/client'
import type { HistoryPoint } from '../api/types'
import ChartCard from '../components/ChartCard.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import LoadingState from '../components/LoadingState.vue'
import StatCard from '../components/StatCard.vue'
import { baseOptions, lineStyle } from '../charts/options'
import { readChartTheme, withAlpha } from '../charts/theme'
import { useAsync } from '../composables/useAsync'
import { useTheme } from '../composables/useTheme'
import {
  formatCompact,
  formatDate,
  formatDateTime,
  formatDecimal,
  formatInteger,
  formatSigned,
  formatSignedPercent,
} from '../utils/format'

const props = defineProps<{ owner: string; name: string }>()
const { theme } = useTheme()

const { data: history, error, run } = useAsync((signal, owner: string, name: string) =>
  api.history(owner, name, signal),
)
watch(
  () => [props.owner, props.name] as const,
  ([owner, name]) => void run(owner, name),
  { immediate: true },
)

type Metric = keyof Pick<
  HistoryPoint,
  'stars' | 'forks' | 'open_issues' | 'contributors_count' | 'commits_last_30_days' | 'average_weekly_commits'
>

// One chart per metric: their scales differ by orders of magnitude, and a shared or dual
// axis would distort the comparison.
const METRICS: { key: Metric; label: string; integer: boolean }[] = [
  { key: 'stars', label: 'Stars', integer: true },
  { key: 'forks', label: 'Forks', integer: true },
  { key: 'open_issues', label: 'Open issues & PRs', integer: true },
  { key: 'contributors_count', label: 'Contributors', integer: true },
  { key: 'commits_last_30_days', label: 'Commits in last 30 days', integer: true },
  { key: 'average_weekly_commits', label: 'Average commits per week', integer: false },
]

const chartTheme = computed(() => readChartTheme(theme.value))

const labels = computed(() => {
  const points = history.value?.points ?? []
  const days = points.map((p) => formatDate(p.analyzed_at))
  // Several snapshots on one day need the time to stay distinguishable.
  const ambiguous = new Set(days).size !== days.length
  return ambiguous ? points.map((p) => formatDateTime(p.analyzed_at)) : days
})

const chartData = computed(() => {
  const color = chartTheme.value.series[0] ?? '#338ced'
  const points = history.value?.points ?? []
  return Object.fromEntries(
    METRICS.map((metric): [Metric, ChartData<'line', (number | null)[], string>] => [
      metric.key,
      {
        labels: labels.value,
        datasets: [
          {
            label: metric.label,
            data: points.map((p) => p[metric.key]),
            borderColor: color,
            backgroundColor: withAlpha(color, 0.12),
            fill: 'start',
            ...lineStyle,
            pointRadius: points.length <= 12 ? 3 : 0,
          },
        ],
      },
    ]),
  ) as Record<Metric, ChartData<'line', (number | null)[], string>>
})

const integerOptions = computed(() =>
  baseOptions<'line'>(chartTheme.value, { integerTicks: true, beginAtZero: false }),
)
const decimalOptions = computed(() =>
  baseOptions<'line'>(chartTheme.value, { integerTicks: false, beginAtZero: false }),
)

const singleSnapshot = computed(() => (history.value?.points.length ?? 0) < 2)
</script>

<template>
  <div class="page">
    <ErrorAlert v-if="error" :message="error" retryable @retry="run(owner, name)" />
    <LoadingState v-else-if="!history" label="Loading history…" />

    <template v-else>
      <section class="card header">
        <div>
          <h1>
            <a :href="history.html_url" target="_blank" rel="noopener">{{ history.full_name }}</a>
          </h1>
          <p class="muted">
            {{ history.points.length }} snapshots from {{ formatDate(history.points[0]?.analyzed_at) }} to
            {{ formatDate(history.points.at(-1)?.analyzed_at) }}.
          </p>
        </div>
        <RouterLink
          v-if="history.points.length"
          class="button"
          :to="{ name: 'analysis', params: { id: history.points.at(-1)!.analysis_id } }"
        >
          Latest analysis
        </RouterLink>
      </section>

      <div v-if="singleSnapshot" class="alert warning small" role="note">
        Only one snapshot so far. Re-analyze the repository later to see how its statistics change.
      </div>

      <section class="stats-grid cols-3" aria-label="Change since first snapshot">
        <StatCard
          v-for="metric in METRICS"
          :key="metric.key"
          :label="metric.label"
          :value="metric.integer ? formatCompact(history.changes[metric.key]?.last) : formatDecimal(history.changes[metric.key]?.last)"
          :hint="`${formatSigned(history.changes[metric.key]?.absolute)} (${formatSignedPercent(history.changes[metric.key]?.percent)}) since first`"
        />
      </section>

      <div v-if="!singleSnapshot" class="grid grid-3">
        <ChartCard v-for="metric in METRICS" :key="metric.key" :title="metric.label" :height="200">
          <Line
            :data="chartData[metric.key]"
            :options="metric.integer ? integerOptions : decimalOptions"
          />
          <template #table>
            <table class="data">
              <thead><tr><th>Analyzed</th><th class="right">{{ metric.label }}</th></tr></thead>
              <tbody>
                <tr v-for="point in history.points" :key="point.analysis_id">
                  <td>{{ formatDateTime(point.analyzed_at) }}</td>
                  <td class="right">
                    {{ metric.integer ? formatInteger(point[metric.key]) : formatDecimal(point[metric.key]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </ChartCard>
      </div>

      <section class="card">
        <header class="card-header"><h2>Snapshots</h2></header>
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Analyzed</th>
                <th class="right">Stars</th>
                <th class="right">Forks</th>
                <th class="right">Open issues</th>
                <th class="right">Contributors</th>
                <th class="right">Total commits</th>
                <th class="right">Commits / 30d</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="point in [...history.points].reverse()" :key="point.analysis_id">
                <td>
                  <RouterLink :to="{ name: 'analysis', params: { id: point.analysis_id } }">
                    {{ formatDateTime(point.analyzed_at) }}
                  </RouterLink>
                </td>
                <td class="right">{{ formatInteger(point.stars) }}</td>
                <td class="right">{{ formatInteger(point.forks) }}</td>
                <td class="right">{{ formatInteger(point.open_issues) }}</td>
                <td class="right">{{ formatInteger(point.contributors_count) }}</td>
                <td class="right">{{ formatInteger(point.total_commits) }}</td>
                <td class="right">{{ formatInteger(point.commits_last_30_days) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.header h1 a {
  color: var(--text-primary);
}
.header p {
  margin: 0.4rem 0 0;
}
</style>
