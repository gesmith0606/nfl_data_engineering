/**
 * Motion primitives (Phase 62-04, DSGN-03)
 *
 * Token-backed wrappers around `motion/react`. Each primitive reads durations
 * from `MOTION` / easings from `EASE` in `@/lib/design-tokens`, honors
 * `prefers-reduced-motion: reduce` (pass-through render when reduced), and
 * forwards props to the inner element.
 *
 * Do NOT write raw `<motion.div>` or inline `transition={{ duration: ... }}`
 * in app/feature code — route through these primitives.
 *
 * Sanctioned exceptions (must still import `MOTION` + `EASE` from design-tokens
 * so durations/easings stay uniform):
 *   - Looping animations (e.g. typing-indicator dots) — not an entrance/exit
 *   - `AnimatePresence` exit animations — FadeIn is entrance-only by design
 *   - Shared-layout animations via `layoutId`
 *
 * Known constraints:
 *   - `Stagger` is a Client Component and wraps each child in a motion.div.
 *     Passing a Server Component as a child will fail at the React server/client
 *     boundary. Hoist the RSC up (render it yourself, stagger only its siblings)
 *     or materialize the RSC in a parent Client Component first.
 */

'use client';

import * as React from 'react';
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type HTMLMotionProps,
  type Transition
} from 'motion/react';
import { MOTION, EASE, STAGGER_STEP } from '@/lib/design-tokens';

type DivMotionProps = Omit<HTMLMotionProps<'div'>, 'children'>;

function PassThrough({ children, className, style }: { children: React.ReactNode; className?: string; style?: HTMLMotionProps<'div'>['style'] }) {
  return <div className={className} style={style as React.CSSProperties | undefined}>{children}</div>;
}

// --- FadeIn — entrance: fade + subtle rise. Default MOTION.base (220ms). ---

export interface FadeInProps extends DivMotionProps {
  children: React.ReactNode;
  delay?: number;
  /** Vertical rise offset in px. Ignored when `slide` is set. */
  rise?: number;
  /** Horizontal slide offset in px. Positive = slide in from the right. */
  slide?: number;
  duration?: keyof typeof MOTION;
}

export function FadeIn({ children, delay = 0, rise = 8, slide, duration = 'base', className, style, ...rest }: FadeInProps) {
  const reduceMotion = useReducedMotion();
  if (reduceMotion) return <PassThrough className={className} style={style}>{children}</PassThrough>;
  const from = slide !== undefined ? { opacity: 0, x: slide } : { opacity: 0, y: rise };
  const to = slide !== undefined ? { opacity: 1, x: 0 } : { opacity: 1, y: 0 };
  return (
    <motion.div
      initial={from}
      animate={to}
      transition={{ duration: MOTION[duration], delay, ease: EASE.outStandard }}
      className={className}
      style={style}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

// --- Stagger — cascades children. 10 items at default step ≈ 640ms. ---

export interface StaggerProps extends DivMotionProps {
  children: React.ReactNode;
  step?: number;
  delay?: number;
}

export function Stagger({ children, step = STAGGER_STEP, delay = 0, className, style, ...rest }: StaggerProps) {
  const reduceMotion = useReducedMotion();
  if (reduceMotion) return <PassThrough className={className} style={style}>{children}</PassThrough>;
  // Preserve original child keys so list reorders animate correctly. React.Children.map
  // prefixes keys with `.$` but keeps the original segment intact after the prefix;
  // we still fall back to the map index for childless / keyless fragments.
  const itemVariants = {
    hidden: { opacity: 0, y: 6 },
    visible: { opacity: 1, y: 0, transition: { duration: MOTION.base, ease: EASE.outStandard } }
  };
  return (
    <motion.div
      initial='hidden'
      animate='visible'
      variants={{ hidden: {}, visible: { transition: { staggerChildren: step, delayChildren: delay } } }}
      className={className}
      style={style}
      {...rest}
    >
      {React.Children.map(children, (child, idx) => {
        const key = React.isValidElement(child) && child.key !== null ? child.key : idx;
        return (
          <motion.div key={key} variants={itemVariants}>
            {child}
          </motion.div>
        );
      })}
    </motion.div>
  );
}

// --- HoverLift — card/surface hover feedback (MOTION.fast). ---

export interface HoverLiftProps extends DivMotionProps {
  children: React.ReactNode;
  lift?: number;
  scale?: number;
}

export function HoverLift({ children, lift = 2, scale = 1, className, style, ...rest }: HoverLiftProps) {
  const reduceMotion = useReducedMotion();
  if (reduceMotion) return <PassThrough className={className} style={style}>{children}</PassThrough>;
  return (
    <motion.div
      whileHover={{ y: -lift, scale }}
      transition={{ duration: MOTION.fast, ease: EASE.outStandard }}
      className={className}
      style={style}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

// --- PressScale — button/badge press-down (MOTION.instant = 100ms). ---

export interface PressScaleProps extends DivMotionProps {
  children: React.ReactNode;
  scale?: number;
}

export function PressScale({ children, scale = 0.97, className, style, ...rest }: PressScaleProps) {
  const reduceMotion = useReducedMotion();
  if (reduceMotion) return <PassThrough className={className} style={style}>{children}</PassThrough>;
  return (
    <motion.div
      whileTap={{ scale }}
      transition={{ duration: MOTION.instant, ease: EASE.outStandard }}
      className={className}
      style={style}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

// --- DataLoadReveal — skeleton → content crossfade. ---

export interface DataLoadRevealProps {
  loading: boolean;
  skeleton: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function DataLoadReveal({ loading, skeleton, children, className }: DataLoadRevealProps) {
  const reduceMotion = useReducedMotion();
  const transition: Transition = { duration: MOTION.base, ease: EASE.outStandard };
  if (reduceMotion) return <div className={className}>{loading ? skeleton : children}</div>;
  return (
    <div className={className}>
      <AnimatePresence mode='wait' initial={false}>
        {loading ? (
          <motion.div key='skeleton' initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={transition}>
            {skeleton}
          </motion.div>
        ) : (
          <motion.div key='content' initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={transition}>
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
