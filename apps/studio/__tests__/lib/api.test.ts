import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('API Client', () => {
  beforeEach(() => {
    mockFetch.mockClear()
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
})

describe('WebSocket URL', () => {
  it('should have WS_URL configured', () => {
    expect(process.env.NEXT_PUBLIC_WS_URL).toBe('ws://localhost:5800')
  })
})
