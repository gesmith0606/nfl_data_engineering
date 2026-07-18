import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SleeperLeagueView } from '../sleeper-league-view';
import { sleeperLogin, fetchLeagueOverview } from '@/lib/nfl/api';
import type { LeagueOverviewResponse } from '@/lib/nfl/types';

vi.mock('@/components/ui/infobar', () => ({
  useInfobar: () => ({ setContent: vi.fn() })
}));

// League-home fetchers stay pending — these tests end at/just past the wizard.
// (vi.mock is hoisted, so the factory must be self-contained.)
vi.mock('@/lib/nfl/api', () => ({
  sleeperLogin: vi.fn(),
  fetchLeagueOverview: vi.fn(),
  fetchLeagueRosterReport: vi.fn(() => new Promise(() => {})),
  fetchLeagueWaivers: vi.fn(() => new Promise(() => {})),
  fetchLeagueDraftPrep: vi.fn(() => new Promise(() => {})),
  fetchLeagueMyWeek: vi.fn(() => new Promise(() => {}))
}));

const USER = {
  user_id: 'U1',
  username: 'george',
  display_name: 'George',
  avatar: null
};
const LEAGUE = {
  league_id: 'L1',
  name: 'Test League',
  season: '2026',
  total_rosters: 12,
  sport: 'nfl',
  status: 'in_season',
  settings: null
};

const OVERVIEW: LeagueOverviewResponse = {
  league_id: 'L1',
  league_name: 'Test League',
  season: '2026',
  status: 'in_season',
  total_rosters: 12,
  roster_positions: ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX'],
  scoring_format_label: 'Full PPR (league)',
  scoring_deltas: [],
  unmodeled_keys: [],
  user_roster: [
    {
      sleeper_player_id: 'P1',
      player_name: 'Patrick Mahomes',
      position: 'QB',
      team: 'KC',
      projected_season_points: 380,
      vorp: 90
    },
    {
      sleeper_player_id: 'P2',
      player_name: 'Breece Hall',
      position: 'RB',
      team: 'NYJ',
      projected_season_points: 250,
      vorp: 60
    }
  ],
  team_name: 'Waffle Stompers'
};

async function walkToConfirmStep() {
  render(<SleeperLeagueView />);
  fireEvent.change(screen.getByLabelText('Sleeper username'), {
    target: { value: 'george' }
  });
  fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
  fireEvent.click(await screen.findByText('Test League'));
}

describe('SleeperLeagueView — roster-confirm team identity (H-4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(sleeperLogin).mockResolvedValue({
      user: USER,
      leagues: [LEAGUE]
    });
    vi.mocked(fetchLeagueOverview).mockResolvedValue({ ...OVERVIEW });
  });

  it('previews team name, roster count, and scoring before commit', async () => {
    await walkToConfirmStep();

    expect(await screen.findByText('Waffle Stompers')).toBeInTheDocument();
    expect(screen.getByText(/2 players rostered/)).toBeInTheDocument();
    expect(screen.getByText(/Full PPR \(league\)/)).toBeInTheDocument();
    // Prefetch happened on step entry, before any confirm click
    expect(fetchLeagueOverview).toHaveBeenCalledWith('L1', 'U1');
  });

  it('falls back to "Team <display name>" when no team name is set', async () => {
    vi.mocked(fetchLeagueOverview).mockResolvedValue({
      ...OVERVIEW,
      team_name: null
    });
    await walkToConfirmStep();

    expect(await screen.findByText('Team George')).toBeInTheDocument();
  });

  it('commits using the prefetched overview', async () => {
    await walkToConfirmStep();
    await screen.findByText('Waffle Stompers');
    // Only the wizard prefetch has run at this point
    expect(fetchLeagueOverview).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm & Sync' }));
    // Connected view renders after commit (league tab + heading both show it)
    expect((await screen.findAllByText('Test League')).length).toBeGreaterThan(0);
    // The saved entry carries the prefetched overview's scoring label
    const saved = JSON.parse(localStorage.getItem('nfl.connectedLeagues') ?? '[]');
    expect(saved[0]?.scoring_format_label).toBe('Full PPR (league)');
  });
});
