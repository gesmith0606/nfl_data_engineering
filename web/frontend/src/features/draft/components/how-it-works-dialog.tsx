'use client'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export type HowItWorksMode = 'landing' | 'board' | 'mock' | 'live'

const CONTENT: Record<HowItWorksMode, { title: string; bullets: string[] }> = {
  landing: {
    title: 'How this works',
    bullets: [
      'Set your league first — connect Sleeper, pick a platform room, or go custom.',
      'Pick a mode: Mock Draft to practice, Live Co-Pilot to sync a real draft, or the Cheat Sheet Board to track one by hand.',
      "During any draft, Draft means it's your pick and Taken means anyone else's — recommendations update after every pick."
    ]
  },
  board: {
    title: 'The cheat sheet board',
    bullets: [
      'Hit Draft when a player is yours, Taken when anyone else takes them — the board and your roster update instantly.',
      "Paste a draft room's pick log any time to catch the whole board up in one shot (Mirror Mode).",
      "Check the Sleepers tab for value the model likes that the market doesn't — vacated-opportunity signal, not just ADP gaps."
    ]
  },
  mock: {
    title: 'Mock draft simulation',
    bullets: [
      'The clock runs on your chosen timer; when it hits zero, autopick drafts from our board so the sim never stalls.',
      'A run of bot picks can be skipped in a burst instead of waiting one at a time.',
      "Undo reverts the last pick — yours or a bot's — if you misclick; a full report card grades every pick when the draft ends."
    ]
  },
  live: {
    title: 'Live draft co-pilot',
    bullets: [
      'Sleeper and Yahoo sync automatically — picks stream in and recommendations update in real time.',
      'ESPN has no public draft API, so it runs in Mirror Mode: paste the pick log any time, or use Draft/Taken like the manual board.',
      "Mirror mode also covers a Yahoo fallback, and either way we track the clock and alert your turn."
    ]
  }
}

interface HowItWorksDialogProps {
  mode: HowItWorksMode
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Hand-rolled first-run guidance dialog (no third-party tour library).
 * Reopenable any time from the "?" button on the landing and in every mode's
 * toolbar; content swaps per mode. Radix Dialog already gives us Escape-to-
 * close and focus trapping for free.
 */
export function HowItWorksDialog({ mode, open, onOpenChange }: HowItWorksDialogProps) {
  const { title, bullets } = CONTENT[mode]
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <ul className='list-disc space-y-[var(--space-2)] py-[var(--space-2)] pl-[var(--space-5)] text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
          {bullets.map(bullet => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  )
}
