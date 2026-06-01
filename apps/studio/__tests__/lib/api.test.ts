import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getSessionAuth, getToken, setAuth } from '@/lib/auth'
import {
  getCreditBalance,
  resolveStreamAuthToken,
  runTemplate,
  runWorkflow,
  subscribeToJob,
} from '@/lib/api'

vi.mock('@/lib/auth', () => ({
  getToken: vi.fn(),
  getSessionAuth: vi.fn(),
  setAuth: vi.fn(),
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
  const mockGetSessionAuth = vi.mocked(getSessionAuth)
  const mockSetAuth = vi.mocked(setAuth)

  beforeEach(() => {
    mockFetch.mockClear()
    mockGetToken.mockReset()
    mockGetSessionAuth.mockReset()
    mockSetAuth.mockReset()
    mockGetToken.mockReturnValue(null)
    mockGetSessionAuth.mockResolvedValue(null)
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

  it('uses the in-memory token for websocket auth when available', async () => {
    mockGetToken.mockReturnValue('jwt.token+with/symbols')

    const ws = await subscribeToJob('job-1', vi.fn())

    expect(ws).toBe(MockWebSocket.instances[0])
    expect(MockWebSocket.instances[0].url).toBe(
      'ws://localhost:5800/v1/jobs/job-1/stream?token=jwt.token%2Bwith%2Fsymbols'
    )
    expect(mockGetSessionAuth).not.toHaveBeenCalled()
  })

  it('bootstraps websocket auth from the session endpoint when needed', async () => {
    mockGetSessionAuth.mockResolvedValue({
      accessToken: 'session.jwt',
      user: { id: 'user-1', email: 'ops@madfam.io' },
    })

    const ws = await subscribeToJob('job-2', vi.fn())

    expect(mockGetSessionAuth).toHaveBeenCalledTimes(1)
    expect(mockSetAuth).toHaveBeenCalledWith('session.jwt', null, {
      id: 'user-1',
      email: 'ops@madfam.io',
    })
    expect(MockWebSocket.instances[0].url).toBe(
      'ws://localhost:5800/v1/jobs/job-2/stream?token=session.jwt'
    )
    expect(ws).toBe(MockWebSocket.instances[0])
  })

  it('returns cached token from resolveStreamAuthToken without session fetch', async () => {
    mockGetToken.mockReturnValue('cached.jwt')

    await expect(resolveStreamAuthToken()).resolves.toBe('cached.jwt')
    expect(mockGetSessionAuth).not.toHaveBeenCalled()
  })

  it('hydrates in-memory auth from resolveStreamAuthToken when needed', async () => {
    mockGetSessionAuth.mockResolvedValue({
      accessToken: 'session.jwt',
      user: { id: 'user-1', email: 'ops@madfam.io' },
    })

    await expect(resolveStreamAuthToken()).resolves.toBe('session.jwt')
    expect(mockSetAuth).toHaveBeenCalledWith('session.jwt', null, {
      id: 'user-1',
      email: 'ops@madfam.io',
    })
  })

  it('returns null from resolveStreamAuthToken when no session exists', async () => {
    await expect(resolveStreamAuthToken()).resolves.toBeNull()
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

  it('fetches credit balance through the server proxy', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ user_id: 'user-1', org_id: null, balance: 2500 }),
    })

    await expect(getCreditBalance()).resolves.toEqual({
      user_id: 'user-1',
      org_id: null,
      balance: 2500,
    })

    expect(mockFetch).toHaveBeenCalledWith('/api/proxy/v1/credits/balance', {})
  })

  it('propagates API errors with APIError', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Not Found' }),
    })

    await expect(runWorkflow('workflow-missing')).rejects.toMatchObject({ status: 404 })
  })

  it('normalizes structured API errors with message fields', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 402,
      json: async () => ({
        detail: {
          message: 'This template requires a paid CEQ entitlement.',
          required_entitlement: 'paid_template',
        },
      }),
    })

    await expect(runTemplate('premium-template', { params: {} })).rejects.toMatchObject({
      status: 402,
      detail: 'This template requires a paid CEQ entitlement.',
      rawDetail: {
        message: 'This template requires a paid CEQ entitlement.',
        required_entitlement: 'paid_template',
      },
    })
  })

  it('propagates network failures', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    await expect(runWorkflow('workflow-fail')).rejects.toThrow('Network error')
  })
})
