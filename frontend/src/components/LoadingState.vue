<script setup lang="ts">
defineProps<{ label?: string }>()
</script>

<template>
  <div class="loading muted" role="status" aria-live="polite">
    <span class="spinner" aria-hidden="true" />
    <span>{{ label ?? 'Loading…' }}</span>
  </div>
</template>

<style scoped>
.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 3rem 1rem;
}
</style>
