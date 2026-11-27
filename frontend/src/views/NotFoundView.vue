<template>
  <div class="page">
    <section class="card empty">
      <h1>Page not found</h1>
      <p class="muted">The page you are looking for does not exist.</p>
      <RouterLink class="button primary" to="/">Analyze a repository</RouterLink>
    </section>
  </div>
</template>

<style scoped>
.empty {
  display: grid;
  justify-items: start;
  gap: 0.75rem;
}
</style>
