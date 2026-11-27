<script setup lang="ts">
import { computed } from 'vue'
import type { LanguageShare } from '../api/types'
import { formatPercent } from '../utils/format'
import { groupLanguages } from '../utils/languages'

const props = defineProps<{ languages: LanguageShare[] }>()

const segments = computed(() => groupLanguages(props.languages))

function color(slot: number | null): string {
  return slot === null ? 'var(--series-other)' : `var(--series-${slot})`
}
</script>

<template>
  <div v-if="segments.length" class="languages">
    <div
      class="bar"
      role="img"
      :aria-label="segments.map((s) => `${s.label} ${formatPercent(s.percentage)}`).join(', ')"
    >
      <span
        v-for="segment in segments"
        :key="segment.label"
        :style="{ flexGrow: segment.percentage, background: color(segment.slot) }"
        :title="`${segment.label}: ${formatPercent(segment.percentage)}`"
      />
    </div>
    <ul class="legend">
      <li v-for="segment in segments" :key="segment.label">
        <span class="dot" :style="{ background: color(segment.slot) }" aria-hidden="true" />
        <span class="name">{{ segment.label }}</span>
        <span class="muted num">{{ formatPercent(segment.percentage) }}</span>
      </li>
    </ul>
  </div>
  <p v-else class="muted">GitHub detected no languages in this repository.</p>
</template>

<style scoped>
.bar {
  display: flex;
  gap: 2px;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
}
.bar span {
  min-width: 3px;
  flex-basis: 0;
}
.legend {
  list-style: none;
  padding: 0;
  margin: 1rem 0 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
  font-size: 0.88rem;
}
.legend li {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.name {
  font-weight: 550;
}
</style>
