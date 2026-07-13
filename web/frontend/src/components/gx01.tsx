import { cn } from '@/lib/utils';

/**
 * GX-01 — the product's mecha assistant figure (sketch 001/002 winners).
 * Pure CSS clip-path anatomy, no image assets. Inspired-by, never literal
 * Gundam: angular armor, yellow V-fin, pulsing cyan eyes, mint chest core.
 *
 * <Gx01Body/> is the full 120x200 figure (desktop hero/feature contexts);
 * <Gx01Head/> is the 44x40 head-only unit (mobile puck, chat launcher).
 * Styles live in src/styles/broadcast.css (.gx / .gxh).
 */

export function Gx01Body({ className }: { className?: string }) {
  return (
    <div className={cn('gx', className)} aria-hidden>
      <div className='fin-l' />
      <div className='fin-r' />
      <div className='head' />
      <div className='visor' />
      <div className='eye l' />
      <div className='eye r' />
      <div className='chin' />
      <div className='neck' />
      <div className='pauldron-l' />
      <div className='pauldron-r' />
      <div className='torso' />
      <div className='vent-l' />
      <div className='vent-r' />
      <div className='core' />
      <div className='arm-l' />
      <div className='arm-r' />
      <div className='fist-l' />
      <div className='fist-r' />
      <div className='waist' />
      <div className='belt' />
      <div className='skirt' />
      <div className='leg-l' />
      <div className='leg-r' />
      <div className='knee-l' />
      <div className='knee-r' />
      <div className='foot-l' />
      <div className='foot-r' />
    </div>
  );
}

export function Gx01Head({ className }: { className?: string }) {
  return (
    <div className={cn('gxh', className)} aria-hidden>
      <div className='fin-l' />
      <div className='fin-r' />
      <div className='head' />
      <div className='visor' />
      <div className='eye l' />
      <div className='eye r' />
      <div className='chin' />
    </div>
  );
}
