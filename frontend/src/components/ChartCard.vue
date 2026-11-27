<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  title: string
  subtitle?: string
  /** Height of the plot area including axis labels. */
  height?: number
}>()

const view = ref<'chart' | 'table'>('chart')
</script>

<template>
  <section class="card">
    <header class="card-header">
      <div>
        <h2>{{ title }}</h2>
        <p v-if="subtitle" class="muted small">{{ subtitle }}</p>
      </div>
      <div class="segmented" role="group" :aria-label="`${title} view`">
        <button type="button" :aria-pressed="view === 'chart'" @click="view = 'chart'">Chart</button>
        <button type="button" :aria-pressed="view === 'table'" @click="view = 'table'">Table</button>
      </div>
    </header>
    <div v-if="view === 'chart'" class="chart-box" :style="{ height: `${height ?? 280}px` }">
      <slot />
    </div>
    <div v-else class="table-wrap" :style="{ maxHeight: `${Math.max(height ?? 280, 320)}px` }">
      <slot name="table" />
    </div>
    <slot name="footer" />
  </section>
</template>
