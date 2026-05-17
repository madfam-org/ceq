import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getToken } from '@/lib/auth'
import { runTemplate, runWorkflow, subscribeToJob } from '@/lib/api'

vi.mock('@/lib/auth', () => ({
  getToken: vi.fn(),
}))

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }
}

describe('API Client', () => {
  const mockGetToken = vi.mocked(getToken)

  beforeEach(() => {
    mockFetch.mockClear()
    mockGetToken.mockReset()
    mockGetToken.mockReturnValue(null)
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  it('routes all Studio API traffic through /api/proxy', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ workflows: [], total: 0 }),
    })

    await runWorkflow('workflow-1', { params: { seed: 42 } })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/proxy/v1/workflows/workflow-1/run',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ params: { seed: 42 } }),
      })
    )
  })

  it('uses the browser token only for websocket auth when available', async () => {
    mockGetToken.mockReturnValue('jwt.token+with/symbols')

    const ws = subscribeToJob('job-1', vi.fn())

    expect(ws).toBe(MockWebSocket.instances[0])
    expect(MockWebSocket.instances[0].url).toBe(
      'ws://localhost:5800/v1/jobs/job-1/stream?token=jwt.token%2Bwith%2Fsymbols'
    )
  })

  it('does not rely on Authorization for REST calls', async () => {
    mockGetToken.mockReturnValue('jwt.token+with/symbols')
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ templates: [], total: 0 }),
    })

    await runTemplate('template-1', { params: { title: 'Launch' } })

    const headers = (mockFetch.mock.calls[0][1] as RequestInit | undefined)?.headers
    expect(headers).toEqual(
      expect.not.objectContaining({ Authorization: 'Bearer jwt.token+with/symbols' })
    )
  })

  it('propagates API errors with APIError', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Not Found' }),
    })

    await expect(runWorkflow('workflow-missing')).rejects.toMatchObject({ status: 404 })
  })

  it('propagates network failures', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    await expect(runWorkflow('workflow-fail')).rejects.toThrow('Network error')
  })
})
