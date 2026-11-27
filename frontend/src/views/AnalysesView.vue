<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, describeError } from '../api/client'
import ErrorAlert from '../components/ErrorAlert.vue'
import LoadingState from '../components/LoadingState.vue'
import { useAsync } from '../composables/useAsync'
import { formatCompact, formatDateTime, formatDecimal } from '../utils/format'
import { splitFullName } from '../utils/repo'

const PAGE_SIZE = 20
const offset = ref(0)
const repositoryFilter = ref('')
const deleteError = ref<string | null>(null)
const deletingId = ref<number | null>(null)

const { data: page, loading, error, run } = useAsync((signal) =>
  api.listAnalyses(
    { limit: PAGE_SIZE, offset: offset.value, repository: repositoryFilter.value.trim() || undefined },
    signal,
  ),
)

const pageNumber = computed(() => Math.floor(offset.value / PAGE_SIZE) + 1)
const pageCount = computed(() => Math.max(1, Math.ceil((page.value?.total ?? 0) / PAGE_SIZE)))

function goTo(newOffset: number): void {
  offset.value = Math.max(0, newOffset)
  void run()
}

function applyFilter(): void {
  offset.value = 0
  void run()
}

async function remove(id: number, fullName: string): Promise<void> {
  if (!window.confirm(`Delete analysis #${id} of ${fullName}? This cannot be undone.`)) return
  deletingId.value = id
  deleteError.value = null
  try {
    await api.deleteAnalysis(id)
    const isLastOnPage = page.value?.items.length === 1 && offset.value > 0
    goTo(isLastOnPage ? offset.value - PAGE_SIZE : offset.value)
  } catch (err) {
    deleteError.value = describeError(err)
  } finally {
    deletingId.value = null
  }
}

onMounted(() => void run())
</script>

<template>
  <div class="page">
    <section class="card">
      <header class="card-header">
        <div>
          <h1>Analysis history</h1>
          <p class="muted small">Every stored analysis, newest first.</p>
        </div>
        <form class="filter" @submit.prevent="applyFilter">
          <input
            v-model="repositoryFilter"
            class="input"
            type="search"
            placeholder="owner/repository"
            aria-label="Filter by repository"
          />
          <button type="submit" class="button">Filter</button>
        </form>
      </header>

      <ErrorAlert v-if="deleteError" :message="deleteError" />
      <ErrorAlert v-if="error" :message="error" retryable @retry="run()" />
      <LoadingState v-else-if="!page" />
      <p v-else-if="page.items.length === 0" class="muted">No analyses found.</p>

      <div v-else class="table-wrap" :class="{ 'is-refreshing': loading }">
        <table class="data">
          <thead>
            <tr>
              <th>Repository</th>
              <th>Analyzed</th>
              <th class="right">Stars</th>
              <th class="right">Forks</th>
              <th class="right">Open issues</th>
              <th class="right">Contributors</th>
              <th class="right">Commits / week</th>
              <th><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in page.items" :key="item.id">
              <td>
                <RouterLink :to="{ name: 'analysis', params: { id: item.id } }">{{ item.full_name }}</RouterLink>
                <div v-if="item.primary_language" class="muted small">{{ item.primary_language }}</div>
              </td>
              <td class="muted small">{{ formatDateTime(item.analyzed_at) }}</td>
              <td class="right">{{ formatCompact(item.stars) }}</td>
              <td class="right">{{ formatCompact(item.forks) }}</td>
              <td class="right">{{ formatCompact(item.open_issues) }}</td>
              <td class="right">{{ formatCompact(item.contributors_count) }}</td>
              <td class="right">{{ formatDecimal(item.average_weekly_commits) }}</td>
              <td class="row-actions">
                <RouterLink
                  class="button ghost small"
                  :to="{ name: 'repository-history', params: splitFullName(item.full_name) }"
                >
                  Trend
                </RouterLink>
                <button
                  type="button"
                  class="button ghost small danger"
                  :disabled="deletingId === item.id"
                  :aria-label="`Delete analysis ${item.id} of ${item.full_name}`"
                  @click="remove(item.id, item.full_name)"
                >
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <nav v-if="page && page.total > PAGE_SIZE" class="pager" aria-label="Pagination">
        <button type="button" class="button small" :disabled="offset === 0 || loading" @click="goTo(offset - PAGE_SIZE)">
          Previous
        </button>
        <span class="muted small">Page {{ pageNumber }} of {{ pageCount }} · {{ page.total }} analyses</span>
        <button
          type="button"
          class="button small"
          :disabled="offset + PAGE_SIZE >= page.total || loading"
          @click="goTo(offset + PAGE_SIZE)"
        >
          Next
        </button>
      </nav>
    </section>
  </div>
</template>

<style scoped>
.filter {
  display: flex;
  gap: 0.5rem;
}
.filter .input {
  min-height: 2.5rem;
  width: 220px;
}
.row-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.25rem;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 1rem;
}
@media (max-width: 640px) {
  .card-header {
    flex-direction: column;
  }
}
</style>
