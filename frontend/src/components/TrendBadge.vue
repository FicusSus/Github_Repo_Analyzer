<script setup lang="ts">
import { computed } from 'vue'
import type { TrendDirection } from '../api/types'

const props = defineProps<{ direction: TrendDirection }>()

const view = computed(() => {
  switch (props.direction) {
    case 'increasing':
      return { icon: '↗', label: 'Increasing' }
    case 'decreasing':
      return { icon: '↘', label: 'Decreasing' }
    case 'stable':
      return { icon: '→', label: 'Stable' }
    default:
      return { icon: '·', label: 'Not enough data' }
  }
})
</script>

<template>
  <span class="badge" :title="`Commit trend over the last 12 complete weeks: ${view.label}`">
    <span aria-hidden="true">{{ view.icon }}</span>{{ view.label }}
  </span>
</template>
