import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, describeError } from './client'

function mockFetch(response: Response | Error): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      if (response instanceof Error) throw response
      return response
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('sends the analyze request as JSON', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 7 }), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await api.analyze('vuejs/core', true)

    expect(result).toEqual({ id: 7 })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/analyses')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ repository: 'vuejs/core', force: true })
  })

  it('serialises repeated query parameters', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await api.compare(['a/b', 'c/d'])

    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/compare?repositories=a%2Fb&repositories=c%2Fd')
  })

  it('maps the backend error envelope to ApiError', async () => {
    mockFetch(
      new Response(
        JSON.stringify({ error: { code: 'github_rate_limited', message: 'Limit', details: {} } }),
        { status: 429, headers: { 'Retry-After': '600' } },
      ),
    )

    const error = await api.getAnalysis(1).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('github_rate_limited')
    expect((error as ApiError).retryAfterSeconds).toBe(600)
    expect(describeError(error)).toBe('GitHub API rate limit reached. Try again in about 10 min.')
  })

  it('handles non-JSON error bodies', async () => {
    mockFetch(new Response('<html>Bad gateway</html>', { status: 502 }))
    const error = (await api.getAnalysis(1).catch((e: unknown) => e)) as ApiError
    expect(error.status).toBe(502)
    expect(error.code).toBe('http_error')
  })

  it('reports network failures', async () => {
    mockFetch(new TypeError('Failed to fetch'))
    const error = (await api.getAnalysis(1).catch((e: unknown) => e)) as ApiError
    expect(error.code).toBe('network_error')
  })

  it('returns undefined for 204 responses', async () => {
    mockFetch(new Response(null, { status: 204 }))
    await expect(api.deleteAnalysis(3)).resolves.toBeUndefined()
  })
})
