<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, describeError } from '../api/client'
import { parseRepositoryInput } from '../utils/repo'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })

const router = useRouter()
const input = ref('')
const force = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)
const touched = ref(false)

const parsed = computed(() => parseRepositoryInput(input.value))
const invalid = computed(() => touched.value && input.value.trim() !== '' && parsed.value === null)

async function submit(): Promise<void> {
  touched.value = true
  if (!parsed.value || submitting.value) return
  submitting.value = true
  error.value = null
  try {
    const analysis = await api.analyze(input.value.trim(), force.value)
    await router.push({ name: 'analysis', params: { id: analysis.id } })
    input.value = ''
    touched.value = false
  } catch (err) {
    error.value = describeError(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="search" :class="{ compact }" novalidate @submit.prevent="submit">
    <label class="sr-only" for="repo-input">GitHub repository</label>
    <div class="row">
      <input
        id="repo-input"
        v-model="input"
        class="input"
        type="text"
        inputmode="url"
        autocomplete="off"
        spellcheck="false"
        placeholder="https://github.com/owner/repository or owner/repository"
        :aria-invalid="invalid"
        aria-describedby="repo-input-help"
        :disabled="submitting"
        @blur="touched = true"
      />
      <button class="button primary" type="submit" :disabled="submitting || !parsed">
        <span v-if="submitting" class="spinner" aria-hidden="true" />
        {{ submitting ? 'Analyzing…' : 'Analyze' }}
      </button>
    </div>
    <div class="meta">
      <p id="repo-input-help" class="small" :class="invalid ? 'invalid' : 'muted'">
        {{
          invalid
            ? 'Enter a github.com repository URL or owner/repository.'
            : 'Public repositories only. Analysis takes a few seconds.'
        }}
      </p>
      <label v-if="!compact" class="checkbox">
        <input v-model="force" type="checkbox" />
        Ignore recent cached analysis
      </label>
    </div>
    <div v-if="error" class="alert error small" role="alert">{{ error }}</div>
  </form>
</template>

<style scoped>
.search {
  display: grid;
  gap: 0.6rem;
}
.row {
  display: flex;
  gap: 0.6rem;
}
.meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.meta p {
  margin: 0;
}
.invalid {
  color: var(--critical);
}
.input[aria-invalid='true'] {
  border-color: var(--critical);
}
@media (max-width: 560px) {
  .row {
    flex-direction: column;
  }
}
</style>
