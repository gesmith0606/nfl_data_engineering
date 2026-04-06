'use client';

import { getTeamColor } from '@/lib/nfl/team-colors';

/** NFL division groupings. */
const DIVISIONS: { conference: string; division: string; teams: string[] }[] = [
  { conference: 'AFC', division: 'East', teams: ['BUF', 'MIA', 'NE', 'NYJ'] },
  { conference: 'AFC', division: 'North', teams: ['BAL', 'CIN', 'CLE', 'PIT'] },
  { conference: 'AFC', division: 'South', teams: ['HOU', 'IND', 'JAX', 'TEN'] },
  { conference: 'AFC', division: 'West', teams: ['DEN', 'KC', 'LV', 'LAC'] },
  { conference: 'NFC', division: 'East', teams: ['DAL', 'NYG', 'PHI', 'WAS'] },
  { conference: 'NFC', division: 'North', teams: ['CHI', 'DET', 'GB', 'MIN'] },
  { conference: 'NFC', division: 'South', teams: ['ATL', 'CAR', 'NO', 'TB'] },
  { conference: 'NFC', division: 'West', teams: ['ARI', 'LAR', 'SEA', 'SF'] }
];

interface TeamSelectorProps {
  selectedTeam: string | null;
  onSelectTeam: (team: string) => void;
}

export default function TeamSelector({ selectedTeam, onSelectTeam }: TeamSelectorProps) {
  return (
    <div className='space-y-6'>
      {['AFC', 'NFC'].map((conf) => (
        <div key={conf}>
          <h3 className='text-muted-foreground mb-3 text-sm font-semibold uppercase tracking-wider'>
            {conf}
          </h3>
          <div className='grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4'>
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
    <div className='bg-card rounded-lg border p-3'>
      <div className='text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider'>
        {division}
      </div>
      <div className='grid grid-cols-2 gap-2'>
        {teams.map((team) => {
          const color = getTeamColor(team);
          const isSelected = selectedTeam === team;
          return (
            <button
              key={team}
              onClick={() => onSelectTeam(team)}
              className={`relative flex items-center justify-center rounded-md px-3 py-2.5 text-sm font-bold transition-all focus:outline-none focus:ring-2 focus:ring-offset-1 ${
                isSelected
                  ? 'text-white shadow-md scale-105'
                  : 'bg-muted hover:shadow-sm'
              }`}
              style={
                isSelected
                  ? { backgroundColor: color, boxShadow: `0 4px 12px ${color}44` }
                  : { borderLeft: `3px solid ${color}` }
              }
            >
              {team}
            </button>
          );
        })}
      </div>
    </div>
  );
}
