/**
 * Tests for useToast hook
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Use vi.hoisted() to ensure mock is created before vi.mock hoisting
const mockToast = vi.hoisted(() =>
  Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
  })
)

vi.mock('sonner', () => ({
  toast: mockToast,
}))

// Import after mocking
import { useToast, toast } from '@/hooks/use-toast'

describe('useToast', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns toast function', () => {
    const { result } = renderHook(() => useToast())
    expect(typeof result.current.toast).toBe('function')
  })

  it('shows default toast', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.toast({
        title: 'Test Title',
        description: 'Test Description',
      })
    })

    expect(mockToast).toHaveBeenCalled()
  })

  it('shows destructive toast as error', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.toast({
        title: 'Error Title',
        description: 'Error Description',
        variant: 'destructive',
      })
    })

    expect(mockToast.error).toHaveBeenCalled()
  })
})

describe('toast export', () => {
  it('exports sonner toast directly', () => {
    expect(toast).toBe(mockToast)
  })
})
