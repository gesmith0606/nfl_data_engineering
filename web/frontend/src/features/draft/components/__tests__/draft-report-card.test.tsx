import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DraftReportCard } from '../draft-report-card'
import { fetchMockDraftReport } from '@/lib/nfl/api'
import type { MockDraftReportResponse } from '@/lib/nfl/types'

// vi.mock is hoisted — the factory must be self-contained.
vi.mock('@/lib/nfl/api', () => ({
  fetchMockDraftReport: vi.fn()
}))

const FIXTURE: MockDraftReportResponse = {
  session_id: 's1',
  picks: [
    {
      round: 1,
      overall_pick: 4,
      player_name: 'Bijan Robinson',
      position: 'RB',
      projected_points: 280,
      vorp: 90,
      adp_rank: 8,
      adp_delta: 4,
      best_alternative: { player_name: 'CeeDee Lamb', vorp: 85 },
      vorp_delta: 5
    },
    {
      round: 2,
      overall_pick: 21,
      player_name: 'Reach Guy',
      position: 'WR',
      projected_points: 200,
      vorp: 40,
      adp_rank: 12,
      adp_delta: -9,
      best_alternative: { player_name: 'Better Guy', vorp: 55 },
      vorp_delta: -15
    }
  ],
  summary: {
    total_projected: 1800,
    total_vorp: 210,
    floor_sum: 1500,
    ceiling_sum: 2100,
    letter_grade: 'B',
    grade_notes: ['Strong RB1 value in round 1.', 'Reached for WR in round 2.']
  }
}

function renderCard(sessionId = 's1', enabled = true) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <DraftReportCard sessionId={sessionId} enabled={enabled} />
    </QueryClientProvider>
  )
}

describe('DraftReportCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when not enabled (draft not complete)', () => {
    const { container } = renderCard('s1', false)
    expect(container).toBeEmptyDOMElement()
  })

  it('does not fetch until the "View Draft Report" button is clicked', () => {
    vi.mocked(fetchMockDraftReport).mockResolvedValue(FIXTURE)
    renderCard()
    expect(fetchMockDraftReport).not.toHaveBeenCalled()
  })

  it('renders the grade hero, grade notes, and per-pick steal/reach badges from the fixture', async () => {
    vi.mocked(fetchMockDraftReport).mockResolvedValue(FIXTURE)
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /View Draft Report/ }))

    expect(await screen.findByText('B')).toBeInTheDocument()
    expect(screen.getByText('Strong RB1 value in round 1.')).toBeInTheDocument()
    expect(screen.getByText('Reached for WR in round 2.')).toBeInTheDocument()

    expect(screen.getByText('Bijan Robinson')).toBeInTheDocument()
    expect(screen.getByText(/CeeDee Lamb/)).toBeInTheDocument()
    expect(screen.getByText('steal')).toBeInTheDocument()
    expect(screen.getByText('reach')).toBeInTheDocument()

    expect(screen.getByText(/Floor 1500 \/ Ceiling 2100/)).toBeInTheDocument()
  })
})
