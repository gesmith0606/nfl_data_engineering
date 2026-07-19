import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UndoButton } from '../undo-button'

describe('UndoButton', () => {
  it('calls onUndo when clicked', () => {
    const onUndo = vi.fn()
    render(<UndoButton label='Undo my last pick' onUndo={onUndo} isPending={false} isConflict={false} />)

    fireEvent.click(screen.getByRole('button', { name: /Undo my last pick/ }))
    expect(onUndo).toHaveBeenCalledTimes(1)
  })

  it('disables and shows a tooltip after a 409 (nothing to undo)', () => {
    render(<UndoButton label='Undo my last pick' onUndo={vi.fn()} isPending={false} isConflict />)

    const button = screen.getByRole('button', { name: /Undo my last pick/ })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'Nothing to undo')
  })

  it('disables while pending, without the conflict tooltip', () => {
    render(<UndoButton label='Undo my last pick' onUndo={vi.fn()} isPending isConflict={false} />)

    const button = screen.getByRole('button', { name: /Undo my last pick/ })
    expect(button).toBeDisabled()
    expect(button).not.toHaveAttribute('title')
  })

  it('is enabled with no tooltip in the default state', () => {
    render(<UndoButton label='Undo my last pick' onUndo={vi.fn()} isPending={false} isConflict={false} />)

    const button = screen.getByRole('button', { name: /Undo my last pick/ })
    expect(button).not.toBeDisabled()
    expect(button).not.toHaveAttribute('title')
  })
})
