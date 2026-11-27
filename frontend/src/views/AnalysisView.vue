<script setup lang="ts">
import type { ChartData, ChartOptions } from 'chart.js'
import { computed, ref, watch } from 'vue'
import { Bar, Chart } from 'vue-chartjs'
import { useRouter } from 'vue-router'
import { api, describeError } from '../api/client'
import ChartCard from '../components/ChartCard.vue'
import ErrorAlert from '../components/ErrorAlert.vue'
import LanguageBar from '../components/LanguageBar.vue'
import LoadingState from '../components/LoadingState.vue'
import StatCard from '../components/StatCard.vue'
import TrendBadge from '../components/TrendBadge.vue'
import { barStyle, baseOptions, lineStyle } from '../charts/options'
import { readChartTheme } from '../charts/theme'
import { useAsync } from '../composables/useAsync'
import { useTheme } from '../composables/useTheme'
import {
  formatBucketDay,
  formatBucketMonth,
  formatCompact,
  formatDate,
  formatDateTime,
  formatDecimal,
  formatInteger,
  formatPercent,
  formatRelative,
  formatSignedPercent,
  shortSha,
} from '../utils/format'

const props = defineProps<{ id: number }>()
const router = useRouter()
const { theme } = useTheme()

const { data: analysis, loading, error, run } = useAsync((signal, id: number) =>
  api.getAnalysis(id, signal),
)
watch(
  () => props.id,
  (id) => void run(id),
  { immediate: true },
)

const avatarFailed = ref(false)

function hideBrokenImage(event: Event): void {
  if (event.target instanceof HTMLImageElement) event.target.style.visibility = 'hidden'
}
const reanalyzing = ref(false)
const reanalyzeError = ref<string | null>(null)

async function reanalyze(): Promise<void> {
  if (!analysis.value) return
  reanalyzing.value = true
  reanalyzeError.value = null
  try {
    const fresh = await api.analyze(analysis.value.repository.full_name, true)
    await router.push({ name: 'analysis', params: { id: fresh.id } })
  } catch (err) {
    reanalyzeError.value = describeError(err)
  } finally {
    reanalyzing.value = false
  }
}

const chartTheme = computed(() => readChartTheme(theme.value))
const repo = computed(() => analysis.value?.repository ?? null)
const stats = computed(() => analysis.value?.commit_stats ?? null)
const ownerAndName = computed(() =>
  repo.value ? { owner: repo.value.owner, name: repo.value.name } : null,
)

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const TOP_CONTRIBUTORS = 10

const weeklyData = computed<ChartData<'bar' | 'line', number[], string>>(() => {
  const s = stats.value
  const t = chartTheme.value
  if (!s) return { labels: [], datasets: [] }
  return {
    labels: s.weekly.map((b) => formatBucketDay(b.period_start)),
    datasets: [
      {
        type: 'bar',
        label: 'Commits per week',
        data: s.weekly.map((b) => b.commits),
        backgroundColor: t.series[0],
        hoverBackgroundColor: t.series[0],
        ...barStyle,
        order: 2,
      },
      {
        type: 'line',
        label: '4-week average',
        data: s.rolling_weekly_average.map((b) => b.value),
        borderColor: t.series[1],
        backgroundColor: t.series[1],
        ...lineStyle,
        order: 1,
      },
    ],
  }
})
const weeklyOptions = computed(
  () => baseOptions<'bar'>(chartTheme.value, { legend: true }) as ChartOptions<'bar' | 'line'>,
)

const monthlyData = computed<ChartData<'bar', number[], string>>(() => ({
  labels: stats.value?.monthly.map((b) => formatBucketMonth(b.period_start)) ?? [],
  datasets: [
    {
      label: 'Commits',
      data: stats.value?.monthly.map((b) => b.commits) ?? [],
      backgroundColor: chartTheme.value.series[0],
      ...barStyle,
    },
  ],
}))

const weekdayData = computed<ChartData<'bar', number[], string>>(() => ({
  labels: WEEKDAYS,
  datasets: [
    {
      label: 'Commits',
      data: stats.value?.by_weekday ?? [],
      backgroundColor: chartTheme.value.series[0],
      ...barStyle,
    },
  ],
}))
const singleBarOptions = computed(() => baseOptions<'bar'>(chartTheme.value))

const topContributors = computed(() =>
  (analysis.value?.contributors ?? []).slice(0, TOP_CONTRIBUTORS),
)
const contributorData = computed<ChartData<'bar', number[], string>>(() => ({
  labels: topContributors.value.map((c) => c.login),
  datasets: [
    {
      label: 'Contributions',
      data: topContributors.value.map((c) => c.contributions),
      backgroundColor: chartTheme.value.series[0],
      ...barStyle,
    },
  ],
}))
const contributorOptions = computed(() =>
  baseOptions<'bar'>(chartTheme.value, { horizontal: true }),
)

const trendChange = computed(() => {
  const trend = stats.value?.trend
  if (!trend) return ''
  const change =
    trend.change_percent === null ? 'n/a' : formatSignedPercent(trend.change_percent)
  return `Last 4 weeks: ${formatInteger(trend.last_4_weeks)} commits (${change} vs previous 4)`
})
</script>

<template>
  <div class="page">
    <ErrorAlert v-if="error && !analysis" :message="error" retryable @retry="run(id)" />
    <LoadingState v-else-if="!analysis" label="Loading analysis…" />

    <template v-else-if="repo && stats">
      <section class="card repo-header" :class="{ 'is-refreshing': loading }">
        <img
          v-if="repo.owner_avatar_url && !avatarFailed"
          class="owner-avatar"
          :src="repo.owner_avatar_url"
          alt=""
          width="56"
          height="56"
          @error="avatarFailed = true"
        />
        <span v-else class="owner-avatar placeholder" aria-hidden="true">{{ repo.owner.charAt(0).toUpperCase() }}</span>
        <div class="identity">
          <h1>
            <a :href="repo.html_url" target="_blank" rel="noopener">{{ repo.full_name }}</a>
          </h1>
          <p v-if="repo.description" class="muted">{{ repo.description }}</p>
          <div class="tags">
            <span v-if="repo.is_archived" class="badge">Archived</span>
            <span v-if="repo.is_fork" class="badge">Fork</span>
            <span v-if="repo.license" class="badge">{{ repo.license }}</span>
            <span v-for="topic in repo.topics.slice(0, 8)" :key="topic" class="badge">{{ topic }}</span>
          </div>
          <p class="muted small meta">
            Analyzed {{ formatDateTime(analysis.analyzed_at) }}
            <template v-if="analysis.from_cache"> · served from recent analysis</template>
            · default branch <span class="mono">{{ repo.default_branch }}</span>
            <template v-if="repo.homepage">
              · <a :href="repo.homepage" target="_blank" rel="noopener">homepage</a>
            </template>
          </p>
        </div>
        <div class="actions">
          <button type="button" class="button primary" :disabled="reanalyzing" @click="reanalyze">
            <span v-if="reanalyzing" class="spinner" aria-hidden="true" />
            {{ reanalyzing ? 'Analyzing…' : 'Re-analyze' }}
          </button>
          <RouterLink
            v-if="ownerAndName"
            class="button"
            :to="{ name: 'repository-history', params: ownerAndName }"
          >
            History
          </RouterLink>
          <RouterLink class="button" :to="{ name: 'compare', query: { repos: repo.full_name } }">
            Compare
          </RouterLink>
        </div>
      </section>

      <ErrorAlert v-if="reanalyzeError" :message="reanalyzeError" />
      <div v-if="stats.truncated" class="alert warning small" role="note">
        Very active repository: only the newest {{ formatInteger(stats.commits_analyzed) }} commits
        were fetched, so commit statistics cover {{ formatDate(stats.effective_since) }} – today
        instead of the full {{ stats.window_days }}-day window.
      </div>

      <section class="stats-grid cols-4" aria-label="Key metrics">
        <StatCard label="Stars" :value="formatCompact(analysis.metrics.stars)" />
        <StatCard label="Forks" :value="formatCompact(analysis.metrics.forks)" />
        <StatCard
          label="Open issues & PRs"
          :value="formatCompact(analysis.metrics.open_issues)"
        />
        <StatCard
          label="Contributors"
          :value="formatCompact(analysis.metrics.contributors_count)"
          :hint="analysis.contributor_stats.available ? undefined : 'Not available from GitHub'"
        />
        <StatCard
          label="Total commits"
          :value="formatCompact(analysis.metrics.total_commits)"
          :hint="`on ${repo.default_branch}`"
        />
        <StatCard
          label="Avg commits / week"
          :value="formatDecimal(stats.average_weekly_commits)"
          :hint="`since ${formatDate(stats.effective_since)}`"
        />
        <StatCard
          label="Last commit"
          :value="formatRelative(stats.recent_activity.last_commit_at)"
          :hint="`${stats.recent_activity.commits_last_30_days} commits in 30 days`"
        />
        <StatCard
          label="Created"
          :value="formatDate(repo.created_at)"
          :hint="`last push ${formatRelative(repo.pushed_at)}`"
        />
      </section>

      <div class="grid grid-2">
        <section class="card">
          <header class="card-header">
            <div>
              <h2>Languages</h2>
              <p class="muted small">Share of code bytes detected by GitHub Linguist.</p>
            </div>
          </header>
          <LanguageBar :languages="analysis.languages" />
        </section>

        <section class="card">
          <header class="card-header">
            <div>
              <h2>Contributor concentration</h2>
              <p class="muted small">
                Based on the top {{ analysis.contributor_stats.listed }} contributors (all-time).
              </p>
            </div>
          </header>
          <dl v-if="analysis.contributor_stats.available" class="concentration">
            <div>
              <dt>Bus factor</dt>
              <dd>{{ formatInteger(analysis.contributor_stats.bus_factor) }}</dd>
              <span class="muted small">people behind 50% of contributions</span>
            </div>
            <div>
              <dt>Top contributor</dt>
              <dd>{{ formatPercent(analysis.contributor_stats.top_contributor_share) }}</dd>
              <span class="muted small">of contributions</span>
            </div>
            <div>
              <dt>Top 5</dt>
              <dd>{{ formatPercent(analysis.contributor_stats.top_5_share) }}</dd>
              <span class="muted small">of contributions</span>
            </div>
            <div>
              <dt>Gini coefficient</dt>
              <dd>{{ formatDecimal(analysis.contributor_stats.gini_coefficient) }}</dd>
              <span class="muted small">0 = even, 1 = concentrated</span>
            </div>
          </dl>
          <p v-else class="muted">
            GitHub does not list contributors for repositories with very large histories.
          </p>
        </section>
      </div>

      <ChartCard
        title="Weekly commit activity"
        :subtitle="`Default branch, weeks start Monday (UTC). ${trendChange}`"
        :height="300"
      >
        <Chart type="bar" :data="weeklyData" :options="weeklyOptions" />
        <template #table>
          <table class="data">
            <thead>
              <tr><th>Week of</th><th class="right">Commits</th><th class="right">4-week average</th></tr>
            </thead>
            <tbody>
              <tr v-for="(bucket, index) in stats.weekly" :key="bucket.period_start">
                <td>{{ formatBucketDay(bucket.period_start) }}</td>
                <td class="right">{{ bucket.commits }}</td>
                <td class="right">{{ formatDecimal(stats.rolling_weekly_average[index]?.value) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
        <template #footer>
          <p class="trend small muted">
            Trend over the last 12 complete weeks: <TrendBadge :direction="stats.trend.direction" />
          </p>
        </template>
      </ChartCard>

      <div class="grid grid-2">
        <ChartCard title="Commits per month" :height="240">
          <Bar :data="monthlyData" :options="singleBarOptions" />
          <template #table>
            <table class="data">
              <thead><tr><th>Month</th><th class="right">Commits</th></tr></thead>
              <tbody>
                <tr v-for="bucket in stats.monthly" :key="bucket.period_start">
                  <td>{{ formatBucketMonth(bucket.period_start) }}</td>
                  <td class="right">{{ bucket.commits }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </ChartCard>

        <ChartCard title="Commits by weekday" subtitle="Author time, UTC." :height="240">
          <Bar :data="weekdayData" :options="singleBarOptions" />
          <template #table>
            <table class="data">
              <thead><tr><th>Weekday</th><th class="right">Commits</th></tr></thead>
              <tbody>
                <tr v-for="(count, index) in stats.by_weekday" :key="index">
                  <td>{{ WEEKDAYS[index] }}</td>
                  <td class="right">{{ count }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </ChartCard>
      </div>

      <ChartCard
        v-if="analysis.contributors.length"
        title="Top contributors"
        subtitle="All-time commits on the default branch, as reported by GitHub."
        :height="Math.max(160, topContributors.length * 30 + 40)"
      >
        <Bar :data="contributorData" :options="contributorOptions" />
        <template #table>
          <table class="data">
            <thead>
              <tr><th>#</th><th>Contributor</th><th class="right">Contributions</th><th>Share</th></tr>
            </thead>
            <tbody>
              <tr v-for="(contributor, index) in analysis.contributors" :key="contributor.login">
                <td class="muted num">{{ index + 1 }}</td>
                <td>
                  <span class="person">
                    <img
                      v-if="contributor.avatar_url"
                      @error="hideBrokenImage"
                      class="avatar"
                      :src="`${contributor.avatar_url}${contributor.avatar_url.includes('?') ? '&' : '?'}s=48`"
                      alt=""
                      loading="lazy"
                    />
                    <a v-if="contributor.html_url" :href="contributor.html_url" target="_blank" rel="noopener">
                      {{ contributor.login }}
                    </a>
                    <span v-else>{{ contributor.login }}</span>
                    <span v-if="contributor.is_bot" class="badge">bot</span>
                  </span>
                </td>
                <td class="right">{{ formatInteger(contributor.contributions) }}</td>
                <td>
                  <div class="share">
                    <div class="share-bar"><span :style="{ width: `${contributor.percentage}%` }" /></div>
                    <span class="muted small num">{{ formatPercent(contributor.percentage) }}</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </ChartCard>

      <div class="grid grid-2">
        <section class="card">
          <header class="card-header">
            <div>
              <h2>Most active authors</h2>
              <p class="muted small">Commit authors since {{ formatDate(stats.effective_since) }}.</p>
            </div>
          </header>
          <div v-if="stats.active_authors.length" class="table-wrap">
            <table class="data">
              <thead>
                <tr><th>Author</th><th class="right">Commits</th><th class="right">Share</th><th>Last commit</th></tr>
              </thead>
              <tbody>
                <tr v-for="author in stats.active_authors" :key="author.login ?? author.name">
                  <td>
                    {{ author.login ?? author.name }}
                    <span v-if="author.is_bot" class="badge">bot</span>
                    <span v-if="!author.login" class="muted small"> (no GitHub account)</span>
                  </td>
                  <td class="right">{{ formatInteger(author.commits) }}</td>
                  <td class="right">{{ formatPercent(author.percentage) }}</td>
                  <td class="muted small">{{ formatRelative(author.last_commit_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="muted">No commits in the analyzed period.</p>
        </section>

        <section class="card">
          <header class="card-header">
            <div>
              <h2>Recent commits</h2>
              <p class="muted small">
                {{ stats.recent_activity.commits_last_7_days }} commits in the last 7 days by
                {{ stats.recent_activity.active_authors_last_30_days }} authors active this month.
              </p>
            </div>
          </header>
          <ul v-if="analysis.recent_commits.length" class="commits">
            <li v-for="commit in analysis.recent_commits" :key="commit.sha">
              <a v-if="commit.html_url" class="mono" :href="commit.html_url" target="_blank" rel="noopener">
                {{ shortSha(commit.sha) }}
              </a>
              <span v-else class="mono">{{ shortSha(commit.sha) }}</span>
              <div class="commit-text">
                <span class="message">{{ commit.message || '(no message)' }}</span>
                <span class="muted small">
                  {{ commit.author_login ?? commit.author_name }} · {{ formatRelative(commit.authored_at) }}
                </span>
              </div>
            </li>
          </ul>
          <p v-else class="muted">This repository has no commits yet.</p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.repo-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 1.25rem;
  align-items: start;
}
.owner-avatar {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: var(--surface-2);
}
.placeholder {
  display: grid;
  place-items: center;
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text-secondary);
}
.identity {
  display: grid;
  gap: 0.5rem;
}
.identity h1 {
  font-size: 1.5rem;
  word-break: break-word;
}
.identity h1 a {
  color: var(--text-primary);
}
.identity p {
  margin: 0;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.concentration {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem 1.5rem;
  margin: 0;
}
.concentration div {
  display: grid;
}
.concentration dt {
  color: var(--text-secondary);
  font-size: 0.85rem;
}
.concentration dd {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 650;
}
.trend {
  margin: 0.75rem 0 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.person {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
.share {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.share .share-bar {
  flex: 1;
  max-width: 160px;
}
.commits {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
}
.commits li {
  display: grid;
  grid-template-columns: 4.5rem minmax(0, 1fr);
  gap: 0.75rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--border);
}
.commits li:last-child {
  border-bottom: 0;
}
.commit-text {
  display: grid;
  min-width: 0;
}
.message {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 760px) {
  .repo-header {
    grid-template-columns: minmax(0, 1fr);
  }
  .actions {
    justify-content: flex-start;
  }
}
</style>
