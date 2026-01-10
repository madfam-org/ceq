/**
 * Tests for TemplateCard component
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TemplateCard } from '@/components/templates/template-card'

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}))

// Mock next/image
vi.mock('next/image', () => ({
  default: ({ src, alt, fill, ...props }: { src: string; alt: string; fill?: boolean }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} {...props} />
  ),
}))

const mockTemplate = {
  id: 'template-123',
  name: 'Test Template',
  description: 'A test template for creating images',
  category: 'social' as const,
  workflow_json: {},
  input_schema: {},
  tags: ['test', 'image', 'ai'],
  thumbnail_url: 'https://example.com/thumb.jpg',
  preview_urls: [],
  model_requirements: ['sdxl'],
  vram_requirement_gb: 8,
  fork_count: 150,
  run_count: 2500,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
}

describe('TemplateCard', () => {
  it('renders template name', () => {
    render(<TemplateCard template={mockTemplate} />)
    expect(screen.getByText('Test Template')).toBeInTheDocument()
  })

  it('renders template description', () => {
    render(<TemplateCard template={mockTemplate} />)
    expect(screen.getByText('A test template for creating images')).toBeInTheDocument()
  })

  it('renders category badge', () => {
    render(<TemplateCard template={mockTemplate} />)
    expect(screen.getByText('social')).toBeInTheDocument()
  })

  it('renders VRAM requirement', () => {
    render(<TemplateCard template={mockTemplate} />)
    expect(screen.getByText('8GB')).toBeInTheDocument()
  })

  it('formats run count with K suffix', () => {
    render(<TemplateCard template={mockTemplate} />)
    expect(screen.getByText('2.5K runs')).toBeInTheDocument()
  })

  it('renders fork count', () => {
    render(<TemplateCard template={mockTemplate} />)
    expect(screen.getByText('150')).toBeInTheDocument()
  })

  it('shows tags', () => {
    render(<TemplateCard template={mockTemplate} />)

    expect(screen.getByText('test')).toBeInTheDocument()
    expect(screen.getByText('image')).toBeInTheDocument()
    expect(screen.getByText('ai')).toBeInTheDocument()
  })

  it('links to template detail page', () => {
    render(<TemplateCard template={mockTemplate} />)

    const links = screen.getAllByRole('link')
    const templateLinks = links.filter((link) =>
      link.getAttribute('href')?.includes('/templates/social/template-123')
    )
    expect(templateLinks.length).toBeGreaterThan(0)
  })

  it('renders thumbnail image when available', () => {
    render(<TemplateCard template={mockTemplate} />)

    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('src', 'https://example.com/thumb.jpg')
    expect(img).toHaveAttribute('alt', 'Test Template')
  })

  it('shows Run and Fork buttons', () => {
    render(<TemplateCard template={mockTemplate} />)

    expect(screen.getByText('Run')).toBeInTheDocument()
    expect(screen.getByText('Fork')).toBeInTheDocument()
  })

  it('renders without description', () => {
    const templateWithoutDesc = { ...mockTemplate, description: null }
    render(<TemplateCard template={templateWithoutDesc} />)

    expect(screen.getByText('Test Template')).toBeInTheDocument()
  })

  it('renders without thumbnail (shows emoji)', () => {
    const templateWithoutThumb = { ...mockTemplate, thumbnail_url: null }
    render(<TemplateCard template={templateWithoutThumb} />)

    expect(screen.getByText('Test Template')).toBeInTheDocument()
  })

  it('renders with empty tags', () => {
    const templateNoTags = { ...mockTemplate, tags: [] }
    render(<TemplateCard template={templateNoTags} />)

    expect(screen.getByText('Test Template')).toBeInTheDocument()
    expect(screen.queryByText('test')).not.toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<TemplateCard template={mockTemplate} className="custom-class" />)

    const card = container.querySelector('.custom-class')
    expect(card).toBeInTheDocument()
  })

  it('formats million run count with M suffix', () => {
    const popularTemplate = { ...mockTemplate, run_count: 1500000 }
    render(<TemplateCard template={popularTemplate} />)

    expect(screen.getByText('1.5M runs')).toBeInTheDocument()
  })

  it('shows exact count for small numbers', () => {
    const newTemplate = { ...mockTemplate, run_count: 42 }
    render(<TemplateCard template={newTemplate} />)

    expect(screen.getByText('42 runs')).toBeInTheDocument()
  })
})
