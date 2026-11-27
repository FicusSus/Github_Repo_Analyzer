<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type { TrackedRepository } from '../api/types'
import ErrorAlert from '../components/ErrorAlert.vue'
import LoadingState from '../components/LoadingState.vue'
import RepoSearch from '../components/RepoSearch.vue'
import { useAsync } from '../composables/useAsync'
import { formatCompact, formatRelative } from '../utils/format'
import { splitFullName } from '../utils/repo'

const PAGE_SIZE = 12
const search = ref('')
const items = ref<TrackedRepository[]>([])
const total = ref(0)

const { loading, error, run } = useAsync(async (signal, offset: number) => {
  const page = await api.listRepositories(
    { limit: PAGE_SIZE, offset, search: search.value.trim() || undefined },
    signal,
  )
  items.value = offset === 0 ? page.items : [...items.value, ...page.items]
  total.value = page.total
  return page
})

let debounce: number | undefined
watch(search, () => {
  window.clearTimeout(debounce)
  debounce = window.setTimeout(() => void run(0), 250)
})

onMounted(() => void run(0))
</script>

<template>
  <div class="page">
    <section class="hero card">
      <div>
        <h1>Analyze a GitHub repository</h1>
        <p class="muted">
          Commit activity, language mix, contributor concentration and how they change over time —
          for any public repository, no GitHub token required.
        </p>
      </div>
      <RepoSearch />
    </section>

    <section class="card">
      <header class="card-header">
        <div>
          <h2>Analyzed repositories</h2>
          <p class="muted small">Latest snapshot of every repository analyzed on this server.</p>
        </div>
        <input
          v-model="search"
          class="input filter"
          type="search"
          placeholder="Filter by name"
          aria-label="Filter analyzed repositories"
        />
      </header>

      <ErrorAlert v-if="error" :message="error" retryable @retry="run(0)" />
      <LoadingState v-else-if="loading && items.length === 0" />
      <p v-else-if="items.length === 0" class="muted empty">
        {{ search ? 'No analyzed repository matches this filter.' : 'Nothing analyzed yet. Try “pallets/flask” or “vuejs/core”.' }}
      </p>

      <ul v-else class="repo-grid" :class="{ 'is-refreshing': loading }">
        <li v-for="repo in items" :key="repo.full_name" class="repo">
          <RouterLink :to="{ name: 'analysis', params: { id: repo.latest.id } }" class="repo-name">
            {{ repo.full_name }}
          </RouterLink>
          <p class="description muted small">{{ repo.latest.description ?? 'No description' }}</p>
          <dl class="facts small">
            <div><dt>Stars</dt><dd>{{ formatCompact(repo.latest.stars) }}</dd></div>
            <div><dt>Forks</dt><dd>{{ formatCompact(repo.latest.forks) }}</dd></div>
            <div><dt>Commits / 30d</dt><dd>{{ formatCompact(repo.latest.commits_last_30_days) }}</dd></div>
          </dl>
          <footer class="small muted">
            <span v-if="repo.latest.primary_language" class="badge">{{ repo.latest.primary_language }}</span>
            <span>Analyzed {{ formatRelative(repo.last_analyzed_at) }}</span>
            <RouterLink
              v-if="repo.analyses_count > 1"
              :to="{ name: 'repository-history', params: splitFullName(repo.full_name) }"
            >
              {{ repo.analyses_count }} snapshots
            </RouterLink>
          </footer>
        </li>
      </ul>

      <div v-if="items.length < total" class="more">
        <button type="button" class="button" :disabled="loading" @click="run(items.length)">
          Show more ({{ total - items.length }})
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.hero {
  display: grid;
  gap: 1.25rem;
  padding: 2rem;
}
.hero p {
  margin: 0.4rem 0 0;
  max-width: 62ch;
}
.filter {
  max-width: 240px;
  min-height: 2.25rem;
}
.empty {
  padding: 1.5rem 0;
  margin: 0;
}
.repo-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
}
.repo {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1rem;
  display: grid;
  gap: 0.5rem;
  align-content: start;
}
.repo-name {
  font-weight: 650;
  word-break: break-word;
}
.description {
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.6em;
}
.facts {
  display: flex;
  gap: 1.25rem;
  margin: 0;
}
.facts dt {
  color: var(--text-secondary);
}
.facts dd {
  margin: 0;
  font-weight: 650;
  font-size: 1rem;
}
.repo footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
}
.more {
  display: flex;
  justify-content: center;
  margin-top: 1rem;
}
@media (max-width: 560px) {
  .card-header {
    flex-direction: column;
  }
  .filter {
    max-width: none;
  }
}
</style>
