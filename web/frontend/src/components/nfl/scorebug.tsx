import Link from 'next/link';
import { getTeamColor } from '@/lib/nfl/team-colors';
import { TEAM_SECONDARY_COLORS } from '@/lib/nfl/team-meta';
import { cn } from '@/lib/utils';

/**
 * Broadcast scorebug — the product's signature component (sketch 001/005
 * winners, see .claude/skills/sketch-findings-nfl-data-engineering).
 *
 * Near-black pill with a multicolor gradient outline, mint score panels with
 * near-black digits, trophy emblem separator. The clock tab above carries OUR
 * predicted line; the optional ribbon below is a CTA. `compact` renders the
 * grid-sized variant; `verdict` renders the graded receipts treatment
 * (hits keep the mint outline, misses go gray but stay on the board).
 */

export interface ScorebugProps {
  awayTeam: string;
  homeTeam: string;
  awayScore: number | string;
  homeScore: number | string;
  /** Content for the black clock tab above the pill, e.g. `OUR LINE  KC −2.5`. */
  clockTab?: string;
  /** Right-side detail block lines (yellow condensed caps), e.g. ['Wk 1 · SNF', 'Edge: High']. */
  detail?: string[];
  /** Ribbon CTA under the pill (full size only). */
  ribbon?: string;
  /** Navigation target for the ribbon — renders a real link (RSC-safe). */
  ribbonHref?: string;
  onRibbonClick?: () => void;
  compact?: boolean;
  /** Graded receipts state — 'hit' | 'miss'. Misses stay visible (gray). */
  verdict?: 'hit' | 'miss';
  /** Upcoming-game conviction tag — 'high' renders EDGE, 'med' renders LEAN. */
  edge?: 'high' | 'med';
  className?: string;
}

function TeamChip({ team }: { team: string }) {
  const primary = getTeamColor(team);
  const secondary = TEAM_SECONDARY_COLORS[team.toUpperCase()] ?? '#8892ad';
  return (
    <span
      className='bug-chip'
      style={{ background: `linear-gradient(135deg, ${primary} 60%, ${secondary})` }}
      aria-hidden
    />
  );
}

export function Scorebug({
  awayTeam,
  homeTeam,
  awayScore,
  homeScore,
  clockTab,
  detail,
  ribbon,
  ribbonHref,
  onRibbonClick,
  compact = false,
  verdict,
  edge,
  className
}: ScorebugProps) {
  return (
    <div className={cn('bug', compact && 'compact', verdict, className)}>
      {clockTab && !compact && <div className='bug-clock'>{clockTab}</div>}
      {verdict && (
        <span className={cn('bug-verdict', verdict)}>
          {verdict === 'hit' ? '✓ COVER' : '✗ MISS'}
        </span>
      )}
      {!verdict && edge && (
        <span className={cn('bug-edge-tag', edge === 'med' && 'med')}>
          {edge === 'high' ? 'EDGE' : 'LEAN'}
        </span>
      )}
      <div className='bug-row'>
        <div className='bug-team away'>
          <span className='bug-name'>{awayTeam}</span>
          <TeamChip team={awayTeam} />
        </div>
        <div className='bug-scorepanel'>
          <div className='bug-score'>{awayScore}</div>
          <div className='bug-sep'>
            <div className='bug-emblem' />
          </div>
          <div className='bug-score'>{homeScore}</div>
        </div>
        <div className='bug-team'>
          <TeamChip team={homeTeam} />
          <span className='bug-name'>{homeTeam}</span>
        </div>
        {detail && detail.length > 0 && (
          <div className='bug-detail'>
            {detail.map((line, i) => (
              <span key={i}>
                {line}
                {i < detail.length - 1 && <br />}
              </span>
            ))}
          </div>
        )}
      </div>
      {ribbon &&
        !compact &&
        (ribbonHref ? (
          <Link href={ribbonHref} className='bug-ribbon'>
            {ribbon}
          </Link>
        ) : onRibbonClick ? (
          <div
            className='bug-ribbon'
            onClick={onRibbonClick}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onRibbonClick();
            }}
            role='button'
            tabIndex={0}
          >
            {ribbon}
          </div>
        ) : (
          // No target → decorative label; keeps the component usable from
          // Server Components (functions can't cross the RSC boundary).
          <div className='bug-ribbon'>{ribbon}</div>
        ))}
    </div>
  );
}
