import { onBeforeUnmount, ref, shallowRef, type Ref, type ShallowRef } from 'vue'
import { describeError } from '../api/client'

export interface AsyncState<T, A extends unknown[]> {
  data: ShallowRef<T | null>
  error: Ref<string | null>
  rawError: ShallowRef<unknown>
  loading: Ref<boolean>
  run: (...args: A) => Promise<T | null>
}

/**
 * Wraps an async loader with loading/error state. Starting a new run aborts the previous one,
 * so out-of-order responses can never overwrite newer data. The previous data is kept while
 * reloading to avoid layout jumps.
 */
export function useAsync<T, A extends unknown[] = []>(
  loader: (signal: AbortSignal, ...args: A) => Promise<T>,
): AsyncState<T, A> {
  const data = shallowRef<T | null>(null)
  const error = ref<string | null>(null)
  const rawError = shallowRef<unknown>(null)
  const loading = ref(false)
  let controller: AbortController | null = null

  async function run(...args: A): Promise<T | null> {
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = null
    rawError.value = null
    try {
      const result = await loader(current.signal, ...args)
      if (current.signal.aborted) return null
      data.value = result
      return result
    } catch (err) {
      if (current.signal.aborted) return null
      error.value = describeError(err)
      rawError.value = err
      return null
    } finally {
      if (controller === current) loading.value = false
    }
  }

  onBeforeUnmount(() => controller?.abort())

  return { data, error, rawError, loading, run }
}
