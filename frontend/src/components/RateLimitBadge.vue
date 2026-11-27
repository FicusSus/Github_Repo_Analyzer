<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { api } from '../api/client'
import { useAsync } from '../composables/useAsync'
import { formatRelative } from '../utils/format'

const REFRESH_MS = 60_000
const { data, error, run } = useAsync((signal) => api.rateLimit(signal))

let timer: number | undefined
onMounted(() => {
  void run()
  timer = window.setInterval(() => void run(), REFRESH_MS)
})
onBeforeUnmount(() => window.clearInterval(timer))

const low = computed(() => (data.value ? data.value.remaining < data.value.limit * 0.1 : false))
const title = computed(() => {
  if (!data.value) return error.value ?? 'GitHub API budget'
  const mode = data.value.authenticated ? 'authenticated' : 'anonymous'
  return `GitHub API (${mode}): ${data.value.remaining} of ${data.value.limit} requests left, resets ${formatRelative(data.value.reset_at)}`
})
</script>

<template>
  <span class="badge" :class="{ low }" :title="title">
    <span aria-hidden="true">⏱</span>
    <template v-if="data">GitHub API {{ data.remaining }}/{{ data.limit }}</template>
    <template v-else-if="error">GitHub API unavailable</template>
    <template v-else>GitHub API…</template>
  </span>
</template>

<style scoped>
.low {
  color: var(--warning-ink);
  background: var(--warning-bg);
}
</style>
