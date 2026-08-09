import { BroadcastPanel } from '@/components/nfl/broadcast-panel';
import { Skeleton } from '@/components/ui/skeleton';
import { deriveBottomLine, type BottomLinePlayer } from './bottom-line';

export function BottomLinePanelSkeleton() {
  return (
    <BroadcastPanel className='space-y-[var(--space-2)] p-[var(--space-4)]'>
      <Skeleton className='h-[var(--space-3)] w-28' />
      <Skeleton className='h-[var(--space-5)] w-full' />
    </BroadcastPanel>
  );
}

export interface BottomLinePanelProps {
  player: BottomLinePlayer;
  positionPool: number[];
}

/** ESPN "Bottom Line" pattern — one derived verdict sentence, see bottom-line.ts. */
export function BottomLinePanel({ player, positionPool }: BottomLinePanelProps) {
  const verdict = deriveBottomLine(player, positionPool);

  return (
    <BroadcastPanel className='p-[var(--space-4)]'>
      <div
        className='wc-display text-[length:var(--fs-xs)] tracking-[0.14em]'
        style={{ color: 'var(--wc-yellow,#ffd84d)' }}
      >
        Bottom Line
      </div>
      <p className='mt-[var(--space-1)] text-[length:var(--fs-lg)] leading-[var(--lh-lg)] text-white'>
        {verdict}
      </p>
    </BroadcastPanel>
  );
}
