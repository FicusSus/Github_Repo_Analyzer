import { createRouter, createWebHistory } from 'vue-router'
import HomeView from './views/HomeView.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
  routes: [
    { path: '/', name: 'home', component: HomeView, meta: { title: 'Analyze' } },
    {
      path: '/analyses',
      name: 'analyses',
      component: () => import('./views/AnalysesView.vue'),
      meta: { title: 'History' },
    },
    {
      path: '/analyses/:id(\\d+)',
      name: 'analysis',
      component: () => import('./views/AnalysisView.vue'),
      props: (route) => ({ id: Number(route.params.id) }),
      meta: { title: 'Analysis' },
    },
    {
      path: '/repositories/:owner/:name/history',
      name: 'repository-history',
      component: () => import('./views/RepositoryHistoryView.vue'),
      props: true,
      meta: { title: 'Repository history' },
    },
    {
      path: '/compare',
      name: 'compare',
      component: () => import('./views/CompareView.vue'),
      meta: { title: 'Compare' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('./views/NotFoundView.vue'),
      meta: { title: 'Not found' },
    },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : null
  document.title = title ? `${title} · GitHub Repository Analyzer` : 'GitHub Repository Analyzer'
})
