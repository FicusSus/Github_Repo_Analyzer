<script setup lang="ts">
import type { ChartData } from 'chart.js'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Bar, Line } from 'vue-chartjs'
import { useRoute, useRouter } from 'vue-router'
import { api, describeError } from '../api/client'
import type { ComparedRepository } from '../api/types'
import ChartCard from '../components/ChartCard.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import LoadingState from '../components/LoadingState.vue'
import TrendBadge from '../components/TrendBadge.vue'
import { barStyle, baseOptions, lineStyle } from '../charts/options'
import { readChartTheme } from '../charts/theme'
import { useAsync } from '../composables/useAsync'
import { useTheme } from '../composables/useTheme'
import {
  formatBucketDay,
  formatCompact,
  formatDate,
  formatDaysAgo,
  formatDecimal,
  formatInteger,
  formatPercent,
} from '../utils/format'
import { parseRepositoryInput } from '../utils/repo'

const MAX_SELECTED = 5
const MAX_LANGUAGES = 8

const route = useRoute()
const router = useRouter()
const { theme } = useTheme()
const chartTheme = computed(() => readChartTheme(theme.value))

// ------------------------------------------------------------------ selection (URL is the source of truth)

function queryRepos(): string[] {
  const raw = route.query.repos
  const values = Array.isArray(raw) ? raw : raw ? [raw] : []
  return [...new Set(values.filter((v): v is string => typeof v === 'string' && v.length > 0))].slice(
    0,
    MAX_SELECTED,
  )
}

const selected = computed(() => queryRepos())

/** Each repository keeps its colour slot while selected, so removing one never repaints others. */
const slots = reactive(new Map<string, number>())
watch(
  selected,
  (repos) => {
    const keys = new Set(repos.map((r) => r.toLowerCase()))
    for (const key of [...slots.keys()]) if (!keys.has(key)) slots.delete(key)
    for (const repo of repos) {
      const key = repo.toLowerCase()
      if (slots.has(key)) continue
      const used = new Set(slots.values())
      let slot = 1
      while (used.has(slot)) slot += 1
      slots.set(key, slot)
    }
  },
  { immediate: true },
)

function colorOf(fullName: string): string {
  const slot = slots.get(fullName.toLowerCase()) ?? 1
  return chartTheme.value.series[slot - 1] ?? chartTheme.value.other
}

function setSelection(repos: string[]): void {
  void router.replace({ query: { ...route.query, repos } })
}

function toggle(fullName: string): void {
  const current = selected.value
  const exists = current.some((r) => r.toLowerCase() === fullName.toLowerCase())
  if (exists) setSelection(current.filter((r) => r.toLowerCase() !== fullName.toLowerCase()))
  else if (current.length < MAX_SELECTED) setSelection([...current, fullName])
}

function isSelected(fullName: string): boolean {
  return selected.value.some((r) => r.toLowerCase() === fullName.toLowerCase())
}

// ------------------------------------------------------------------ data

const tracked = useAsync((signal) => api.listRepositories({ limit: 100, offset: 0 }, signal))
onMounted(() => void tracked.run())

const comparison = useAsync((signal, repos: string[]) => api.compare(repos, signal))
watch(
  selected,
  (repos) => {
    if (repos.length >= 2) void comparison.run(repos)
  },
  { immediate: true },
)

const addInput = ref('')
const adding = ref(false)
const addError = ref<string | null>(null)

async function addRepository(): Promise<void> {
  const parsed = parseRepositoryInput(addInput.value)
  if (!parsed) {
    addError.value = 'Enter a github.com repository URL or owner/repository.'
    return
  }
  if (selected.value.length >= MAX_SELECTED) {
    addError.value = `You can compare up to ${MAX_SELECTED} repositories.`
    return
  }
  adding.value = true
  addError.value = null
  try {
    // Analyzing returns the canonical name and reuses a recent analysis when one exists.
    const analysis = await api.analyze(addInput.value.trim())
    addInput.value = ''
    if (!isSelected(analysis.repository.full_name)) {
      setSelection([...selected.value, analysis.repository.full_name])
    }
    void tracked.run()
  } catch (err) {
    addError.value = describeError(err)
  } finally {
    adding.value = false
  }
}

// ------------------------------------------------------------------ charts

const repos = computed<ComparedRepository[]>(() => comparison.data.value?.repositories ?? [])

const weeklyData = computed<ChartData<'line', (number | null)[], string>>(() => {
  const activity = comparison.data.value?.weekly_activity
  if (!activity) return { labels: [], datasets: [] }
  return {
    labels: activity.weeks.map(formatBucketDay),
    datasets: repos.value.map((repo) => ({
      label: repo.full_name,
      data: activity.series[repo.full_name] ?? [],
      borderColor: colorOf(repo.full_name),
      backgroundColor: colorOf(repo.full_name),
      spanGaps: false,
      ...lineStyle,
    })),
  }
})
const weeklyOptions = computed(() => baseOptions<'line'>(chartTheme.value, { legend: true }))

const languageRows = computed(() => (comparison.data.value?.languages ?? []).slice(0, MAX_LANGUAGES))
const languageData = computed<ChartData<'bar', number[], string>>(() => ({
  labels: languageRows.value.map((row) => row.language),
  datasets: repos.value.map((repo) => ({
    label: repo.full_name,
    data: languageRows.value.map((row) => row.shares[repo.full_name] ?? 0),
    backgroundColor: colorOf(repo.full_name),
    ...barStyle,
    maxBarThickness: 14,
  })),
}))
const languageOptions = computed(() => {
  const options = baseOptions<'bar'>(chartTheme.value, {
    legend: true,
    horizontal: true,
    integerTicks: false,
  })
  const x = options.scales?.x
  if (x?.ticks) x.ticks.callback = (value) => `${value}%`
  if (x) x.max = 100
  return options
})

// ------------------------------------------------------------------ metrics table

type NumericKey =
  | 'stars'
  | 'forks'
  | 'open_issues'
  | 'contributors_count'
  | 'total_commits'
  | 'average_weekly_commits'
  | 'commits_last_30_days'
  | 'bus_factor'

const METRIC_ROWS: { key: NumericKey; label: string; decimal?: boolean }[] = [
  { key: 'stars', label: 'Stars' },
  { key: 'forks', label: 'Forks' },
  { key: 'open_issues', label: 'Open issues & PRs' },
  { key: 'contributors_count', label: 'Contributors' },
  { key: 'total_commits', label: 'Total commits' },
  { key: 'average_weekly_commits', label: 'Avg commits / week', decimal: true },
  { key: 'commits_last_30_days', label: 'Commits in last 30 days' },
  { key: 'bus_factor', label: 'Bus factor' },
]

function leaderOf(key: NumericKey): number | null {
  const values = repos.value.map((r) => r[key]).filter((v): v is number => v !== null)
  return values.length ? Math.max(...values) : null
}
</script>

<template>
  <div class="page">
    <section class="card">
      <header class="card-header">
        <div>
          <h1>Compare repositories</h1>
          <p class="muted small">
            Pick 2–{{ MAX_SELECTED }} repositories. The latest stored analysis of each is compared.
          </p>
        </div>
      </header>

      <div class="picker">
        <form class="add" @submit.prevent="addRepository">
          <input
            v-model="addInput"
            class="input"
            type="text"
            placeholder="Add any repository: owner/repository"
            aria-label="Repository to add to the comparison"
            :disabled="adding"
          />
          <button type="submit" class="button" :disabled="adding || !addInput.trim()">
            <span v-if="adding" class="spinner" aria-hidden="true" />
            {{ adding ? 'Analyzing…' : 'Add' }}
          </button>
        </form>
        <ErrorAlert v-if="addError" :message="addError" />

        <div v-if="tracked.data.value?.items.length" class="chips" role="group" aria-label="Analyzed repositories">
          <button
            v-for="repo in tracked.data.value.items"
            :key="repo.full_name"
            type="button"
            class="chip"
            :aria-pressed="isSelected(repo.full_name)"
            :disabled="!isSelected(repo.full_name) && selected.length >= MAX_SELECTED"
            @click="toggle(repo.full_name)"
          >
            <span
              v-if="isSelected(repo.full_name)"
              class="swatch"
              :style="{ background: colorOf(repo.full_name) }"
              aria-hidden="true"
            />
            {{ repo.full_name }}
          </button>
        </div>
        <p v-else-if="tracked.error.value" class="muted small">{{ tracked.error.value }}</p>
      </div>
    </section>

    <p v-if="selected.length < 2" class="card muted">Select at least two repositories to compare.</p>
    <template v-else>
      <ErrorAlert
        v-if="comparison.error.value"
        :message="comparison.error.value"
        retryable
        @retry="comparison.run(selected)"
      />
      <LoadingState v-else-if="!comparison.data.value" label="Comparing…" />

      <template v-if="comparison.data.value && repos.length">
        <section class="card" :class="{ 'is-refreshing': comparison.loading.value }">
          <header class="card-header"><h2>Key metrics</h2></header>
          <div class="table-wrap">
            <table class="data compare-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th v-for="repo in repos" :key="repo.full_name" class="right">
                    <span class="swatch" :style="{ background: colorOf(repo.full_name) }" aria-hidden="true" />
                    <RouterLink :to="{ name: 'analysis', params: { id: repo.analysis_id } }">
                      {{ repo.full_name }}
                    </RouterLink>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in METRIC_ROWS" :key="row.key">
                  <td>{{ row.label }}</td>
                  <td
                    v-for="repo in repos"
                    :key="repo.full_name"
                    class="right"
                    :class="{ leader: repos.length > 1 && repo[row.key] !== null && repo[row.key] === leaderOf(row.key) }"
                  >
                    {{ row.decimal ? formatDecimal(repo[row.key]) : formatCompact(repo[row.key]) }}
                  </td>
                </tr>
                <tr>
                  <td>Primary language</td>
                  <td v-for="repo in repos" :key="repo.full_name" class="right">{{ repo.primary_language ?? '—' }}</td>
                </tr>
                <tr>
                  <td>Last commit</td>
                  <td v-for="repo in repos" :key="repo.full_name" class="right">
                    {{ formatDaysAgo(repo.days_since_last_commit) }}
                  </td>
                </tr>
                <tr>
                  <td>Commit trend</td>
                  <td v-for="repo in repos" :key="repo.full_name" class="right">
                    <TrendBadge :direction="repo.trend" />
                  </td>
                </tr>
                <tr>
                  <td>Created</td>
                  <td v-for="repo in repos" :key="repo.full_name" class="right">{{ formatDate(repo.repo_created_at) }}</td>
                </tr>
                <tr>
                  <td>Analyzed</td>
                  <td v-for="repo in repos" :key="repo.full_name" class="right muted small">
                    {{ formatDate(repo.analyzed_at) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="muted small note">The highest value of each numeric metric is shown in bold.</p>
        </section>

        <ChartCard
          title="Weekly commit activity"
          subtitle="Commits per week on each default branch (last 52 weeks). Gaps mean the week is outside that repository's analyzed window."
          :height="300"
        >
          <Line :data="weeklyData" :options="weeklyOptions" />
          <template #table>
            <table class="data">
              <thead>
                <tr>
                  <th>Week of</th>
                  <th v-for="repo in repos" :key="repo.full_name" class="right">{{ repo.full_name }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(week, index) in comparison.data.value.weekly_activity.weeks" :key="week">
                  <td>{{ formatBucketDay(week) }}</td>
                  <td v-for="repo in repos" :key="repo.full_name" class="right">
                    {{ formatInteger(comparison.data.value.weekly_activity.series[repo.full_name]?.[index]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </ChartCard>

        <ChartCard
          title="Language distribution"
          :subtitle="`Share of code per repository, top ${MAX_LANGUAGES} languages.`"
          :height="Math.max(220, languageRows.length * (repos.length * 16 + 18) + 60)"
        >
          <Bar :data="languageData" :options="languageOptions" />
          <template #table>
            <table class="data">
              <thead>
                <tr>
                  <th>Language</th>
                  <th v-for="repo in repos" :key="repo.full_name" class="right">{{ repo.full_name }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in comparison.data.value.languages" :key="row.language">
                  <td>{{ row.language }}</td>
                  <td v-for="repo in repos" :key="repo.full_name" class="right">
                    {{ formatPercent(row.shares[repo.full_name]) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </ChartCard>
      </template>
    </template>
  </div>
</template>

<style scoped>
.picker {
  display: grid;
  gap: 0.9rem;
}
.add {
  display: flex;
  gap: 0.5rem;
  max-width: 560px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.85rem;
  cursor: pointer;
}
.chip[aria-pressed='true'] {
  background: var(--surface-2);
  color: var(--text-primary);
  font-weight: 600;
}
.chip:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.swatch {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 2px;
  margin-right: 0.35rem;
}
.chip .swatch {
  margin-right: 0;
}
.compare-table td.leader {
  font-weight: 700;
}
.note {
  margin: 0.75rem 0 0;
}
</style>
