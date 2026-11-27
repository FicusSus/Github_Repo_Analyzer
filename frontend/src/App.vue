<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import RateLimitBadge from './components/RateLimitBadge.vue'
import { useTheme } from './composables/useTheme'

const { theme, toggle } = useTheme()
</script>

<template>
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="app-header">
    <div class="container inner">
      <RouterLink to="/" class="brand">
        <img src="/favicon.svg" alt="" width="26" height="26" />
        <span>Repo Analyzer</span>
      </RouterLink>
      <nav aria-label="Main">
        <RouterLink to="/" exact-active-class="active">Analyze</RouterLink>
        <RouterLink to="/analyses" active-class="active">History</RouterLink>
        <RouterLink to="/compare" active-class="active">Compare</RouterLink>
      </nav>
      <div class="tools">
        <RateLimitBadge class="hide-sm" />
        <button
          type="button"
          class="button ghost small"
          :aria-label="`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`"
          @click="toggle"
        >
          {{ theme === 'dark' ? '☀' : '☾' }}
        </button>
      </div>
    </div>
  </header>
  <main id="main" class="container">
    <RouterView />
  </main>
</template>

<style scoped>
.skip-link {
  position: absolute;
  left: -999px;
}
.skip-link:focus {
  left: 1rem;
  top: 0.5rem;
  z-index: 10;
  background: var(--surface-1);
  padding: 0.4rem 0.8rem;
  border-radius: var(--radius-sm);
}
.app-header {
  position: sticky;
  top: 0;
  z-index: 5;
  background: color-mix(in srgb, var(--page) 88%, transparent);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
}
.inner {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  min-height: 3.5rem;
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  color: var(--text-primary);
  font-weight: 700;
}
.brand:hover {
  text-decoration: none;
}
nav {
  display: flex;
  gap: 0.25rem;
}
nav a {
  color: var(--text-secondary);
  padding: 0.35rem 0.7rem;
  border-radius: var(--radius-sm);
  font-weight: 550;
}
nav a:hover {
  color: var(--text-primary);
  text-decoration: none;
  background: var(--surface-2);
}
nav a.active {
  color: var(--text-primary);
  background: var(--surface-2);
}
.tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
@media (max-width: 640px) {
  .hide-sm,
  .brand span {
    display: none;
  }
  .inner {
    gap: 0.75rem;
  }
}
</style>
