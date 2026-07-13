'use client';

import { Card } from '@/components/ui/card';
import type { GamePrediction } from '../api/types';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { TEAM_SECONDARY_COLORS } from '@/lib/nfl/team-meta';

/**
 * Scores ledger (sketch 005-C winner) — the audit-table view of the weekly
 * slate. Our line sits directly beside the market line (the disagreement IS
 * the product), with ●/◐/○ edge glyphs. Graded ✓/✗ results join this table
 * once the grading feed is exposed through the API.
 */

const EDGE_HIGH = 3.0;
const EDGE_MED = 1.5;

function edgeLevel(p: GamePrediction): 'high' | 'med' | 'low' {
  const top = Math.max(Math.abs(p.spread_edge ?? 0), Math.abs(p.total_edge ?? 0));
  if (top >= EDGE_HIGH) return 'high';
  if (top >= EDGE_MED) return 'med';
  return 'low';
}

const EDGE_GLYPH = { high: '● HIGH', med: '◐ MED', low: '○ LOW' } as const;

function TeamChip({ team }: { team: string }) {
  const primary = getTeamColor(team);
  const secondary = TEAM_SECONDARY_COLORS[team.toUpperCase()] ?? '#8892ad';
  return (
    <span
      className='inline-block h-[15px] w-[23px] shrink-0 rounded-[2.5px] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.25)]'
      style={{ background: `linear-gradient(135deg, ${primary} 60%, ${secondary})` }}
      aria-hidden
    />
  );
}

function fmtLine(value: number | null): string {
  if (value === null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}`;
}

export function PredictionLedger({ predictions }: { predictions: GamePrediction[] }) {
  // Conviction-first ordering: the games we disagree with the market on lead.
  const rows = [...predictions].sort((a, b) => {
    const order = { high: 0, med: 1, low: 2 };
    return order[edgeLevel(a)] - order[edgeLevel(b)];
  });

  return (
    <Card className='overflow-hidden'>
      <div className='wc-broadcast-table overflow-x-auto'>
        <table className='w-full min-w-[820px] text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          <thead className='bg-muted/50'>
            <tr>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>Game</th>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Our Spread</th>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Market</th>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Our Total</th>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Market</th>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>Edge</th>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>ATS Pick</th>
              <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>O/U Pick</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const level = edgeLevel(p);
              return (
                <tr key={p.game_id} className='border-b border-border/50'>
                  <td className='px-[var(--space-3)] py-[var(--space-3)]'>
                    <span className='flex items-center gap-[var(--space-2)] font-semibold'>
                      <TeamChip team={p.away_team} />
                      {p.away_team}
                      <span className='text-xs text-muted-foreground'>@</span>
                      <TeamChip team={p.home_team} />
                      {p.home_team}
                    </span>
                  </td>
                  <td className='px-[var(--space-3)] py-[var(--space-3)] text-right'>
                    <span className='wc-num-hero !text-[17px]'>
                      {fmtLine(p.predicted_spread)}
                    </span>
                  </td>
                  <td className='px-[var(--space-3)] py-[var(--space-3)] text-right text-muted-foreground tabular-nums'>
                    {fmtLine(p.vegas_spread)}
                  </td>
                  <td className='px-[var(--space-3)] py-[var(--space-3)] text-right'>
                    <span className='wc-num-hero !text-[17px]'>
                      {p.predicted_total.toFixed(1)}
                    </span>
                  </td>
                  <td className='px-[var(--space-3)] py-[var(--space-3)] text-right text-muted-foreground tabular-nums'>
                    {p.vegas_total !== null ? p.vegas_total.toFixed(1) : '—'}
                  </td>
                  <td className='px-[var(--space-3)] py-[var(--space-3)]'>
                    <span className={`wc-edge-glyph ${level}`}>{EDGE_GLYPH[level]}</span>
                  </td>
                  <td className='px-[var(--space-3)] py-[var(--space-3)] font-medium'>
                    {p.ats_pick || '—'}
                  </td>
                  <td className='px-[var(--space-3)] py-[var(--space-3)] font-medium'>
                    {p.ou_pick || '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
