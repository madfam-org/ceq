import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock Next.js router
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}))

// Mock environment variables
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:5800'
process.env.NEXT_PUBLIC_WS_URL = 'ws://localhost:5800'
process.env.NEXT_PUBLIC_JANUA_DOMAIN = 'auth.madfam.io'
process.env.NEXT_PUBLIC_JANUA_CLIENT_ID = 'test-client-id'
