import type { Column } from '@tanstack/react-table';
import type { CSSProperties } from 'react';

interface PinningStylesOptions<TData> {
  column: Column<TData>;
  withBorder?: boolean;
}

export function getCommonPinningStyles<TData>({
  column,
  withBorder = false,
}: PinningStylesOptions<TData>): CSSProperties {
  const isPinned = column.getIsPinned();
  const isLastLeftPinned = isPinned === 'left' && column.getIsLastColumn('left');
  const isFirstRightPinned =
    isPinned === 'right' && column.getIsFirstColumn('right');

  return {
    boxShadow: withBorder
      ? isLastLeftPinned
        ? '-4px 0 4px -4px hsl(var(--border)) inset'
        : isFirstRightPinned
          ? '4px 0 4px -4px hsl(var(--border)) inset'
          : undefined
      : undefined,
    left: isPinned === 'left' ? `${column.getStart('left')}px` : undefined,
    right: isPinned === 'right' ? `${column.getAfter('right')}px` : undefined,
    opacity: isPinned ? 0.97 : 1,
    position: isPinned ? 'sticky' : 'relative',
    background: isPinned ? 'hsl(var(--background))' : undefined,
    width: column.getSize(),
    zIndex: isPinned ? 1 : 0,
  };
}
