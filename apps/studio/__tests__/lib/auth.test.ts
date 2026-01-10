/**
 * Tests for CEQ Auth utilities
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: () => {
      store = {}
    },
  }
})()

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
})

import {
  getToken,
  getRefreshToken,
  getStoredUser,
  setAuth,
  clearAuth,
  parseJwt,
  isTokenExpired,
  getLoginUrl,
  getLogoutUrl,
  AUTH_CONFIG,
} from '@/lib/auth'

describe('Auth Configuration', () => {
  it('has Janua URL configured', () => {
    expect(AUTH_CONFIG.januaUrl).toContain('auth.madfam.io')
  })

  it('has client ID configured', () => {
    expect(AUTH_CONFIG.clientId).toBeDefined()
  })

  it('has redirect URI based on window origin', () => {
    expect(AUTH_CONFIG.redirectUri).toContain('/auth/callback')
  })

  it('has post logout URI based on window origin', () => {
    expect(AUTH_CONFIG.postLogoutUri).toBeDefined()
  })
})

describe('Token Storage', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.clearAllMocks()
    // Reset mock return values
    localStorageMock.getItem.mockReturnValue(null)
  })

  it('getToken returns null when no token', () => {
    const token = getToken()
    expect(token).toBeNull()
  })

  it('getToken returns stored token', () => {
    localStorageMock.getItem.mockReturnValue('test-token')

    const token = getToken()
    expect(token).toBe('test-token')
  })

  it('getRefreshToken returns null when no token', () => {
    localStorageMock.getItem.mockReturnValue(null)
    const token = getRefreshToken()
    expect(token).toBeNull()
  })

  it('getRefreshToken returns stored token', () => {
    localStorageMock.getItem.mockReturnValue('refresh-token')

    const token = getRefreshToken()
    expect(token).toBe('refresh-token')
  })

  it('getStoredUser returns null when no user', () => {
    const user = getStoredUser()
    expect(user).toBeNull()
  })

  it('getStoredUser returns parsed user', () => {
    const mockUser = { id: 'user-123', email: 'test@example.com' }
    localStorageMock.getItem.mockReturnValue(JSON.stringify(mockUser))

    const user = getStoredUser()
    expect(user).toEqual(mockUser)
  })

  it('getStoredUser handles invalid JSON', () => {
    localStorageMock.getItem.mockReturnValue('invalid-json')

    const user = getStoredUser()
    expect(user).toBeNull()
  })

  it('setAuth stores all auth data', () => {
    const user = { id: 'user-123', email: 'test@example.com' }
    setAuth('access-token', 'refresh-token', user)

    expect(localStorageMock.setItem).toHaveBeenCalledWith('janua_token', 'access-token')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('janua_refresh_token', 'refresh-token')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('janua_user', JSON.stringify(user))
  })

  it('setAuth handles null refresh token', () => {
    const user = { id: 'user-123', email: 'test@example.com' }
    setAuth('access-token', null, user)

    expect(localStorageMock.setItem).toHaveBeenCalledWith('janua_token', 'access-token')
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('janua_refresh_token', expect.anything())
  })

  it('clearAuth removes all auth data', () => {
    clearAuth()

    expect(localStorageMock.removeItem).toHaveBeenCalledWith('janua_token')
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('janua_refresh_token')
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('janua_user')
  })
})

describe('JWT Parsing', () => {
  // Create a test JWT with base64url encoding
  function createTestJwt(payload: object): string {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
    const body = btoa(JSON.stringify(payload))
    const signature = 'test-signature'
    return `${header}.${body}.${signature}`
  }

  it('parseJwt extracts user from valid token', () => {
    const token = createTestJwt({
      sub: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
      avatar: 'https://example.com/avatar.jpg',
    })

    const user = parseJwt(token)

    expect(user).toEqual({
      id: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
      avatar: 'https://example.com/avatar.jpg',
    })
  })

  it('parseJwt uses email prefix when no name', () => {
    const token = createTestJwt({
      sub: 'user-123',
      email: 'test@example.com',
    })

    const user = parseJwt(token)

    expect(user?.name).toBe('test')
  })

  it('parseJwt returns null for invalid token', () => {
    const user = parseJwt('invalid-token')
    expect(user).toBeNull()
  })

  it('parseJwt returns null for malformed JWT', () => {
    const user = parseJwt('not.a.valid.jwt')
    expect(user).toBeNull()
  })
})

describe('Token Expiration', () => {
  function createTestJwt(payload: object): string {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
    const body = btoa(JSON.stringify(payload))
    const signature = 'test-signature'
    return `${header}.${body}.${signature}`
  }

  it('isTokenExpired returns true for expired token', () => {
    const expiredToken = createTestJwt({
      sub: 'user-123',
      exp: Math.floor(Date.now() / 1000) - 3600, // 1 hour ago
    })

    expect(isTokenExpired(expiredToken)).toBe(true)
  })

  it('isTokenExpired returns true for token expiring soon', () => {
    const expiringToken = createTestJwt({
      sub: 'user-123',
      exp: Math.floor(Date.now() / 1000) + 30, // 30 seconds from now
    })

    expect(isTokenExpired(expiringToken)).toBe(true)
  })

  it('isTokenExpired returns false for valid token', () => {
    const validToken = createTestJwt({
      sub: 'user-123',
      exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
    })

    expect(isTokenExpired(validToken)).toBe(false)
  })

  it('isTokenExpired returns true for invalid token', () => {
    expect(isTokenExpired('invalid-token')).toBe(true)
  })
})

describe('URL Generation', () => {
  it('getLoginUrl generates authorization URL', () => {
    const url = getLoginUrl()

    expect(url).toContain(AUTH_CONFIG.januaUrl)
    expect(url).toContain('/authorize')
    expect(url).toContain('client_id=')
    expect(url).toContain('redirect_uri=')
    expect(url).toContain('response_type=code')
    expect(url).toContain('scope=openid+profile+email')
  })

  it('getLoginUrl includes returnTo in state', () => {
    const url = getLoginUrl('/dashboard')

    expect(url).toContain('state=%2Fdashboard')
  })

  it('getLogoutUrl generates logout URL', () => {
    const url = getLogoutUrl()

    expect(url).toContain(AUTH_CONFIG.januaUrl)
    expect(url).toContain('/logout')
    expect(url).toContain('client_id=')
    expect(url).toContain('post_logout_redirect_uri=')
  })
})
