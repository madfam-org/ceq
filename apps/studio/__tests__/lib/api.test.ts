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

  it('should have API_URL configured', () => {
    expect(process.env.NEXT_PUBLIC_API_URL).toBe('http://localhost:5800')
  })

  it('should handle successful API responses', async () => {
    const mockData = { workflows: [], total: 0 }
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    })

    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/workflows`)
    const data = await response.json()

    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(data).toEqual(mockData)
  })

  it('should handle API errors', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    })

    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/workflows/unknown`)

    expect(response.ok).toBe(false)
    expect(response.status).toBe(404)
  })

  it('should handle network errors', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    await expect(
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/workflows`)
    ).rejects.toThrow('Network error')
  })

  it('sends workflow run params using the API contract shape', async () => {
    mockGetToken.mockReturnValue('janua-token')
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: 'job-1',
        status: 'queued',
        message: 'queued',
      }),
    })

    await runWorkflow('workflow-1', {
      params: { prompt: 'cosmic nebula', seed: 42 },
      priority: 4,
      webhook_url: 'https://example.com/webhook',
    })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:5800/v1/workflows/workflow-1/run',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          params: { prompt: 'cosmic nebula', seed: 42 },
          priority: 4,
          webhook_url: 'https://example.com/webhook',
        }),
      })
    )
    const request = mockFetch.mock.calls[0][1]
    expect(JSON.parse(request.body)).not.toHaveProperty('input_params')
    expect(request.headers.Authorization).toBe('Bearer janua-token')
  })

  it('sends template run params using the API contract shape', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        job_id: 'job-2',
        status: 'queued',
        message: 'queued',
      }),
    })

    await runTemplate('template-1', {
      params: { title: 'Launch', accent: '#ff00ff' },
      priority: 1,
    })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:5800/v1/templates/template-1/run',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          params: { title: 'Launch', accent: '#ff00ff' },
          priority: 1,
        }),
      })
    )
    expect(JSON.parse(mockFetch.mock.calls[0][1].body)).not.toHaveProperty('input_params')
  })
})

describe('WebSocket URL', () => {
  const mockGetToken = vi.mocked(getToken)

  beforeEach(() => {
    mockGetToken.mockReset()
    mockGetToken.mockReturnValue(null)
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  it('should have WS_URL configured', () => {
    expect(process.env.NEXT_PUBLIC_WS_URL).toBe('ws://localhost:5800')
  })

  it('appends the Janua token required by the job stream endpoint', () => {
    mockGetToken.mockReturnValue('jwt.token+with/symbols')

    const ws = subscribeToJob('job-1', vi.fn())

    expect(ws).toBe(MockWebSocket.instances[0])
    expect(MockWebSocket.instances[0].url).toBe(
      'ws://localhost:5800/v1/jobs/job-1/stream?token=jwt.token%2Bwith%2Fsymbols'
    )
  })

  it('keeps the stream URL query-free when no token is available', () => {
    subscribeToJob('job-2', vi.fn())

    expect(MockWebSocket.instances[0].url).toBe(
      'ws://localhost:5800/v1/jobs/job-2/stream'
    )
  })
})
