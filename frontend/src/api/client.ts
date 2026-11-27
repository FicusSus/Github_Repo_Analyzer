import type {
  AnalysisDetail,
  AnalysisSummary,
  ApiErrorBody,
  Comparison,
  Page,
  RateLimitInfo,
  RepositoryHistory,
  TrackedRepository,
} from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const DEFAULT_TIMEOUT_MS = 60_000

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown> | undefined
  readonly retryAfterSeconds: number | null

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
    retryAfterSeconds: number | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.retryAfterSeconds = retryAfterSeconds
  }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item))
    else params.append(key, String(value))
  }
  const search = params.toString()
  return `${BASE_URL}/api${path}${search ? `?${search}` : ''}`
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const error = (value as { error: unknown }).error
  return typeof error === 'object' && error !== null && 'message' in error && 'code' in error
}

async function request<T>(
  method: 'GET' | 'POST' | 'DELETE',
  path: string,
  options: { query?: Query; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(DEFAULT_TIMEOUT_MS)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      signal,
      headers: options.body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError' && options.signal?.aborted) {
      throw error
    }
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError(0, 'timeout', 'The server took too long to respond.')
    }
    throw new ApiError(0, 'network_error', 'Cannot reach the server. Is the backend running?')
  }

  if (response.status === 204) return undefined as T

  let payload: unknown = null
  const text = await response.text()
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const retryAfter = Number(response.headers.get('Retry-After'))
    const retryAfterSeconds = Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null
    if (isErrorBody(payload)) {
      const { code, message, details } = payload.error
      throw new ApiError(response.status, code, message, details, retryAfterSeconds)
    }
    throw new ApiError(
      response.status,
      'http_error',
      `Request failed with status ${response.status}.`,
      undefined,
      retryAfterSeconds,
    )
  }
  return payload as T
}

export const api = {
  analyze(repository: string, force = false, signal?: AbortSignal) {
    return request<AnalysisDetail>('POST', '/analyses', { body: { repository, force }, signal })
  },
  getAnalysis(id: number, signal?: AbortSignal) {
    return request<AnalysisDetail>('GET', `/analyses/${id}`, { signal })
  },
  listAnalyses(params: { limit: number; offset: number; repository?: string }, signal?: AbortSignal) {
    return request<Page<AnalysisSummary>>('GET', '/analyses', { query: params, signal })
  },
  deleteAnalysis(id: number) {
    return request<void>('DELETE', `/analyses/${id}`)
  },
  listRepositories(params: { limit: number; offset: number; search?: string }, signal?: AbortSignal) {
    return request<Page<TrackedRepository>>('GET', '/repositories', { query: params, signal })
  },
  latest(owner: string, name: string, signal?: AbortSignal) {
    return request<AnalysisDetail>(
      'GET',
      `/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/latest`,
      { signal },
    )
  },
  history(owner: string, name: string, signal?: AbortSignal) {
    return request<RepositoryHistory>(
      'GET',
      `/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/history`,
      { signal },
    )
  },
  compare(repositories: string[], signal?: AbortSignal) {
    return request<Comparison>('GET', '/compare', { query: { repositories }, signal })
  },
  rateLimit(signal?: AbortSignal) {
    return request<RateLimitInfo>('GET', '/github/rate-limit', { signal })
  },
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'github_rate_limited' && error.retryAfterSeconds) {
      const minutes = Math.ceil(error.retryAfterSeconds / 60)
      return `GitHub API rate limit reached. Try again in about ${minutes} min.`
    }
    return error.message
  }
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}
