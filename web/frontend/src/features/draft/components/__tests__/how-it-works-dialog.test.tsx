import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HowItWorksDialog } from '../how-it-works-dialog'

describe('HowItWorksDialog', () => {
  it('renders mode-specific content for the board', () => {
    render(<HowItWorksDialog mode='board' open onOpenChange={vi.fn()} />)
    expect(screen.getByText('The cheat sheet board')).toBeInTheDocument()
    expect(screen.getByText(/Hit Draft when a player is yours/)).toBeInTheDocument()
  })

  it('renders mode-specific content for mock', () => {
    render(<HowItWorksDialog mode='mock' open onOpenChange={vi.fn()} />)
    expect(screen.getByText('Mock draft simulation')).toBeInTheDocument()
    expect(screen.getByText(/autopick drafts from our board/)).toBeInTheDocument()
  })

  it('renders mode-specific content for live', () => {
    render(<HowItWorksDialog mode='live' open onOpenChange={vi.fn()} />)
    expect(screen.getByText('Live draft co-pilot')).toBeInTheDocument()
    expect(screen.getByText(/Sleeper and Yahoo sync automatically/)).toBeInTheDocument()
  })

  it('renders the landing overview by default', () => {
    render(<HowItWorksDialog mode='landing' open onOpenChange={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'How this works' })).toBeInTheDocument()
  })

  it('closes on Escape, invoking onOpenChange(false)', () => {
    const onOpenChange = vi.fn()
    render(<HowItWorksDialog mode='landing' open onOpenChange={onOpenChange} />)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('renders nothing when closed', () => {
    render(<HowItWorksDialog mode='landing' open={false} onOpenChange={vi.fn()} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
