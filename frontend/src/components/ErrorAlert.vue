<script setup lang="ts">
defineProps<{ message: string; retryable?: boolean }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="alert error" role="alert">
    <span>{{ message }}</span>
    <button v-if="retryable" type="button" class="button small" @click="$emit('retry')">Retry</button>
  </div>
</template>
