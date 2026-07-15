'use client';

import { Card } from '@/components/ui/card';
import type { GamePrediction, GameResult } from '../api/types';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { TEAM_SECONDARY_COLORS } from '@/lib/nfl/team-meta';

/**
 * Scores ledger (sketch 005-C winner) — the audit-table view of the weekly
 * slate. Our line sits directly beside the market line (the disagreement IS
 * the product), with ●/◐/○ edge glyphs. When final scores exist for the
 * week, each pick is graded ✓ COVER / ✗ MISS and the ATS record banner
 * appears — misses stay on the board, that's the point.
 *
 * Grading follows the canonical rules in src/prediction_backtester.py
 * (nflverse convention: positive spread = home favored):
 *   home_covers      = actual_margin > vegas_spread
 *   model_picks_home = predicted_spread > vegas_spread
 *   ats_correct      = !push && home_covers === model_picks_home
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

interface Verdict {
  finalAway: number;
  finalHome: number;
  ats: 'hit' | 'miss' | 'push' | null; // null = ungradable (no vegas line)
  ou: 'hit' | 'miss' | 'push' | null;
}

function gradeGame(p: GamePrediction, g: GameResult | undefined): Verdict | null {
  if (!g || g.home_score === null || g.away_score === null) return null;
  // Older backends coerce unplayed games to 0-0 — never grade those (a real
  // 0-0 final hasn't happened since 1943; a fake MISS verdict is worse than
  // showing the pick).
  if (g.home_score === 0 && g.away_score === 0) return null;
  const margin = g.home_score - g.away_score;
  const total = g.home_score + g.away_score;

  let ats: Verdict['ats'] = null;
  if (p.vegas_spread !== null) {
    if (margin === p.vegas_spread) ats = 'push';
    else {
      const homeCovers = margin > p.vegas_spread;
      const modelPicksHome = p.predicted_spread > p.vegas_spread;
      ats = homeCovers === modelPicksHome ? 'hit' : 'miss';
    }
  }

  let ou: Verdict['ou'] = null;
  if (p.vegas_total !== null && p.ou_pick) {
    if (total === p.vegas_total) ou = 'push';
    else {
      const wentOver = total > p.vegas_total;
      ou = (p.ou_pick.toLowerCase() === 'over') === wentOver ? 'hit' : 'miss';
    }
  }

  return { finalAway: g.away_score, finalHome: g.home_score, ats, ou };
}

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

function VerdictCell({ verdict, kind }: { verdict: Verdict; kind: 'ats' | 'ou' }) {
  const v = verdict[kind];
  if (v === null) return <span className='text-muted-foreground'>—</span>;
  if (v === 'push') return <span className='text-muted-foreground'>PUSH</span>;
  return v === 'hit' ? (
    <span className='font-bold text-[var(--wc-pos,#0eaf7d)]'>✓ COVER</span>
  ) : (
    <span className='font-bold text-[#8892ad]'>✗ MISS</span>
  );
}

function record(verdicts: (Verdict | null)[], kind: 'ats' | 'ou'): string {
  let w = 0;
  let l = 0;
  let push = 0;
  for (const v of verdicts) {
    if (!v || v[kind] === null) continue;
    if (v[kind] === 'hit') w += 1;
    else if (v[kind] === 'miss') l += 1;
    else push += 1;
  }
  return push > 0 ? `${w}–${l}–${push}` : `${w}–${l}`;
}

export function PredictionLedger({
  predictions,
  games = []
}: {
  predictions: GamePrediction[];
  games?: GameResult[];
}) {
  const finals = new Map(games.map((g) => [g.game_id, g]));

  // Conviction-first ordering: the games we disagree with the market on lead.
  const rows = [...predictions]
    .sort((a, b) => {
      const order = { high: 0, med: 1, low: 2 };
      return order[edgeLevel(a)] - order[edgeLevel(b)];
    })
    .map((p) => ({ p, verdict: gradeGame(p, finals.get(p.game_id)) }));

  const verdicts = rows.map((r) => r.verdict);
  const gradedCount = verdicts.filter((v) => v && (v.ats !== null || v.ou !== null)).length;
  const graded = gradedCount > 0;
  const highEdge = rows.filter(
    (r) => edgeLevel(r.p) === 'high' && r.verdict != null && r.verdict.ats !== null
  );
  const highEdgeHits = highEdge.filter((r) => r.verdict?.ats === 'hit').length;

  return (
    <div className='space-y-[var(--gap-stack)]'>
      {/* Graded record banner (sketch 005-C) — only for weeks with finals. */}
      {graded && (
        <div className='flex flex-wrap items-center gap-x-7 gap-y-2 rounded-xl border border-[rgba(145,237,208,0.35)] bg-[rgba(19,23,34,0.8)] px-5 py-3'>
          <div>
            <div className='wc-display text-2xl font-extrabold text-[var(--wc-mint,#91edd0)]'>
              {record(verdicts, 'ats')}
            </div>
            <div className='wc-display text-xs tracking-[0.12em] text-muted-foreground'>
              ATS record
            </div>
          </div>
          <div>
            <div className='wc-display text-2xl font-extrabold text-[var(--wc-mint,#91edd0)]'>
              {record(verdicts, 'ou')}
            </div>
            <div className='wc-display text-xs tracking-[0.12em] text-muted-foreground'>
              O/U record
            </div>
          </div>
          {highEdge.length > 0 && (
            <div>
              <div className='wc-display text-2xl font-extrabold text-[var(--wc-mint,#91edd0)]'>
                {highEdgeHits}/{highEdge.length}
              </div>
              <div className='wc-display text-xs tracking-[0.12em] text-muted-foreground'>
                High-edge hits
              </div>
            </div>
          )}
          <div className='wc-display max-w-[340px] text-xs leading-relaxed tracking-[0.1em] text-muted-foreground'>
            Every pick graded. Misses stay on the board — that&apos;s the point.
          </div>
        </div>
      )}

      <Card className='overflow-hidden'>
        <div className='wc-broadcast-table overflow-x-auto'>
          <table className='w-full min-w-[860px] text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
            <thead className='bg-muted/50'>
              <tr>
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>Game</th>
                {graded && (
                  <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Final</th>
                )}
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Our Spread</th>
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Market</th>
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Our Total</th>
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-right'>Market</th>
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>Edge</th>
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>
                  {graded ? 'ATS Result' : 'ATS Pick'}
                </th>
                <th className='px-[var(--space-3)] py-[var(--space-3)] text-left'>
                  {graded ? 'O/U Result' : 'O/U Pick'}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ p, verdict }) => {
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
                    {graded && (
                      <td className='px-[var(--space-3)] py-[var(--space-3)] text-right font-semibold tabular-nums'>
                        {verdict ? `${verdict.finalAway}–${verdict.finalHome}` : '—'}
                      </td>
                    )}
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
                      {verdict && verdict.ats !== null ? (
                        <VerdictCell verdict={verdict} kind='ats' />
                      ) : (
                        p.ats_pick || '—'
                      )}
                    </td>
                    <td className='px-[var(--space-3)] py-[var(--space-3)] font-medium'>
                      {verdict && verdict.ou !== null ? (
                        <VerdictCell verdict={verdict} kind='ou' />
                      ) : (
                        p.ou_pick || '—'
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
