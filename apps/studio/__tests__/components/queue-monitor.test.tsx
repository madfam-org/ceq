/**
 * Tests for QueueMonitor component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock the hooks
const mockUseJobs = vi.fn()
const mockUseCancelJob = vi.fn()

vi.mock('@/lib/hooks', () => ({
  useJobs: () => mockUseJobs(),
  useCancelJob: () => mockUseCancelJob(),
}))

import { QueueMonitor } from '@/components/queue/queue-monitor'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

const mockJob = (overrides = {}) => ({
  id: 'job-123456789',
  workflow_id: 'workflow-1',
  status: 'running',
  progress: 0.5,
  current_node: 'KSampler',
  error: null,
  input_params: {},
  outputs: [],
  queued_at: '2025-01-01T00:00:00Z',
  started_at: '2025-01-01T00:01:00Z',
  completed_at: null,
  gpu_seconds: 0,
  cold_start_ms: 0,
  worker_id: 'worker-1',
  brand_message: '',
  ...overrides,
})

describe('QueueMonitor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseCancelJob.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    })
  })

  it('shows loading skeleton while fetching', () => {
    mockUseJobs.mockReturnValue({
      isLoading: true,
      error: null,
      data: null,
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    // Should show skeleton placeholders
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows error state when fetch fails', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: new Error('Network error'),
      data: null,
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('Queue offline')).toBeInTheDocument()
    expect(screen.getByText('Network error')).toBeInTheDocument()
  })

  it('shows empty state when no jobs', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: null,
      data: { jobs: [], total: 0 },
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('Queue empty')).toBeInTheDocument()
    expect(screen.getByText('The furnace awaits.')).toBeInTheDocument()
  })

  it('renders running job with progress', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        jobs: [mockJob({ status: 'running', progress: 0.5 })],
        total: 1,
      },
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('job-1234...')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('renders queued job', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        jobs: [mockJob({ status: 'queued', progress: 0 })],
        total: 1,
      },
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('queued')).toBeInTheDocument()
    expect(screen.getByText('In the crucible...')).toBeInTheDocument()
  })

  it('renders completed job with GPU stats', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        jobs: [
          mockJob({
            status: 'completed',
            progress: 1,
            gpu_seconds: 12.5,
            cold_start_ms: 350,
          }),
        ],
        total: 1,
      },
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('completed')).toBeInTheDocument()
    expect(screen.getByText(/12.5s GPU/)).toBeInTheDocument()
  })

  it('renders failed job with error', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        jobs: [
          mockJob({
            status: 'failed',
            error: 'Out of VRAM',
          }),
        ],
        total: 1,
      },
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('failed')).toBeInTheDocument()
    expect(screen.getByText('Out of VRAM')).toBeInTheDocument()
  })

  it('renders cancelled job', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        jobs: [mockJob({ status: 'cancelled' })],
        total: 1,
      },
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('cancelled')).toBeInTheDocument()
    expect(screen.getByText('Aborted')).toBeInTheDocument()
  })

  it('renders multiple jobs', () => {
    mockUseJobs.mockReturnValue({
      isLoading: false,
      error: null,
      data: {
        jobs: [
          mockJob({ id: 'job-111111111', status: 'running' }),
          mockJob({ id: 'job-222222222', status: 'queued' }),
          mockJob({ id: 'job-333333333', status: 'completed' }),
        ],
        total: 3,
      },
    })

    render(<QueueMonitor />, { wrapper: createWrapper() })

    expect(screen.getByText('job-1111...')).toBeInTheDocument()
    expect(screen.getByText('job-2222...')).toBeInTheDocument()
    expect(screen.getByText('job-3333...')).toBeInTheDocument()
  })
})
