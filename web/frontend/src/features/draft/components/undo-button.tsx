'use client'

import { Button } from '@/components/ui/button'
import { Icons } from '@/components/icons'
import { PressScale } from '@/lib/motion-primitives'

interface UndoButtonProps {
  label: string
  onUndo: () => void
  isPending: boolean
  /** True after a 409 ("nothing to undo") — disables the button with an explanatory tooltip. */
  isConflict: boolean
}

/**
 * Shared "Undo" control for both the manual board (POST /draft/undo) and the
 * mock draft view (POST /draft/mock/undo). Disables + shows a tooltip when
 * the last attempt came back 409 (nothing to undo) rather than letting the
 * user keep firing a request that can't succeed.
 */
export function UndoButton({ label, onUndo, isPending, isConflict }: UndoButtonProps) {
  return (
    <PressScale>
      <Button
        variant='outline'
        size='sm'
        onClick={onUndo}
        disabled={isPending || isConflict}
        title={isConflict ? 'Nothing to undo' : undefined}
      >
        {isPending ? (
          <Icons.spinner className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)] animate-spin' />
        ) : (
          <Icons.arrowRight className='mr-1.5 h-[var(--space-4)] w-[var(--space-4)] rotate-180' />
        )}
        {label}
      </Button>
    </PressScale>
  )
}
