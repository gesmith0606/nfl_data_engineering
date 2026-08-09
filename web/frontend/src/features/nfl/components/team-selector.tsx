'use client';

import { getTeamColor } from '@/lib/nfl/team-colors';
import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { WC_KICKER } from '@/features/draft/utils/broadcast-ui';
import { PressScale } from '@/lib/motion-primitives';

/** NFL division groupings. */
const DIVISIONS: { conference: string; division: string; teams: string[] }[] = [
  { conference: 'AFC', division: 'East', teams: ['BUF', 'MIA', 'NE', 'NYJ'] },
  { conference: 'AFC', division: 'North', teams: ['BAL', 'CIN', 'CLE', 'PIT'] },
  { conference: 'AFC', division: 'South', teams: ['HOU', 'IND', 'JAX', 'TEN'] },
  { conference: 'AFC', division: 'West', teams: ['DEN', 'KC', 'LV', 'LAC'] },
  { conference: 'NFC', division: 'East', teams: ['DAL', 'NYG', 'PHI', 'WAS'] },
  { conference: 'NFC', division: 'North', teams: ['CHI', 'DET', 'GB', 'MIN'] },
  { conference: 'NFC', division: 'South', teams: ['ATL', 'CAR', 'NO', 'TB'] },
  // 'LA' (not 'LAR') — nflverse team code used by rosters/schedules/projections.
  { conference: 'NFC', division: 'West', teams: ['ARI', 'LA', 'SEA', 'SF'] }
];

interface TeamSelectorProps {
  selectedTeam: string | null;
  onSelectTeam: (team: string) => void;
}

export default function TeamSelector({ selectedTeam, onSelectTeam }: TeamSelectorProps) {
  return (
    <div className='space-y-[var(--gap-section)]'>
      {['AFC', 'NFC'].map((conf) => (
        <div key={conf}>
          <h3
            className='wc-display mb-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tracking-[0.14em]'
            style={{ color: 'var(--wc-mint,#91edd0)' }}
          >
            {conf}
          </h3>
          <div className='grid grid-cols-1 gap-[var(--gap-stack)] sm:grid-cols-2 lg:grid-cols-4'>
            {DIVISIONS.filter((d) => d.conference === conf).map((div) => (
              <DivisionGroup
                key={`${div.conference}-${div.division}`}
                division={div.division}
                teams={div.teams}
                selectedTeam={selectedTeam}
                onSelectTeam={onSelectTeam}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

interface DivisionGroupProps {
  division: string;
  teams: string[];
  selectedTeam: string | null;
  onSelectTeam: (team: string) => void;
}

function DivisionGroup({ division, teams, selectedTeam, onSelectTeam }: DivisionGroupProps) {
  return (
    <BroadcastPanel rail={false} className='p-[var(--pad-card-sm)]'>
      <div className={`${WC_KICKER} mb-[var(--space-2)]`}>{division}</div>
      <div className='grid grid-cols-2 gap-[var(--space-2)]'>
        {teams.map((team) => {
          const color = getTeamColor(team);
          const isSelected = selectedTeam === team;
          return (
            <PressScale key={team}>
              <button
                onClick={() => onSelectTeam(team)}
                className={`wc-display relative flex h-[var(--tap-min)] w-full items-center justify-center rounded-md px-[var(--space-3)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)] tracking-[0.06em] transition-all focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                  isSelected
                    ? 'text-white shadow-md scale-105'
                    : 'border border-white/10 bg-white/5 text-white/70 hover:border-white/25 hover:text-white'
                }`}
                style={
                  isSelected
                    ? { backgroundColor: color, boxShadow: `0 4px 12px ${color}44` }
                    : { borderLeft: `3px solid ${color}` }
                }
              >
                {team}
              </button>
            </PressScale>
          );
        })}
      </div>
    </BroadcastPanel>
  );
}
