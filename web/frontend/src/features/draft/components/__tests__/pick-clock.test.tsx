import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { act } from 'react'
import { PickClock } from '../pick-clock'

describe('PickClock', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('counts down from timerSeconds as time passes', () => {
    render(<PickClock pickNumber={1} timerSeconds={30} />)

    expect(screen.getByRole('timer')).toHaveTextContent('0:30')

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(screen.getByRole('timer')).toHaveTextContent('0:25')
  })

  it('resets to the full timer when the pick number advances', () => {
    const { rerender } = render(<PickClock pickNumber={1} timerSeconds={30} />)

    act(() => {
      vi.advanceTimersByTime(20000)
    })
    expect(screen.getByRole('timer')).toHaveTextContent('0:10')

    rerender(<PickClock pickNumber={2} timerSeconds={30} />)

    expect(screen.getByRole('timer')).toHaveTextContent('0:30')
  })

  it('renders nothing when timerSeconds is null (e.g. live mode without API timing)', () => {
    const { container } = render(<PickClock pickNumber={1} timerSeconds={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('never counts below zero', () => {
    render(<PickClock pickNumber={1} timerSeconds={5} />)

    act(() => {
      vi.advanceTimersByTime(10000)
    })

    expect(screen.getByRole('timer')).toHaveTextContent('0:00')
  })
})
