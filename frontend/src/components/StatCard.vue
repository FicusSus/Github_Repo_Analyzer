<script setup lang="ts">
defineProps<{
  label: string
  value: string
  hint?: string
}>()
</script>

<template>
  <div class="stat card">
    <span class="label">{{ label }}</span>
    <span class="value">{{ value }}</span>
    <span v-if="hint" class="hint muted small">{{ hint }}</span>
  </div>
</template>

<style scoped>
.stat {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 1rem 1.1rem;
}
.label {
  color: var(--text-secondary);
  font-size: 0.82rem;
}
.value {
  font-size: 1.6rem;
  font-weight: 650;
  letter-spacing: -0.01em;
}
@media (max-width: 560px) {
  .value {
    font-size: 1.3rem;
  }
}
.hint {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
