import { computed, ref } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'
const media = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null

function readStored(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

const explicit = ref<Theme | null>(readStored())
const systemDark = ref(media?.matches ?? true)
media?.addEventListener('change', (event) => {
  systemDark.value = event.matches
})

const theme = computed<Theme>(() => explicit.value ?? (systemDark.value ? 'dark' : 'light'))

/** Shared, app-wide theme state. Charts read it so they re-render when the theme changes. */
export function useTheme() {
  function toggle(): void {
    const next: Theme = theme.value === 'dark' ? 'light' : 'dark'
    explicit.value = next
    document.documentElement.dataset.theme = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Storage can be unavailable (private mode); the choice then lasts for this visit only.
    }
  }
  return { theme, toggle }
}
