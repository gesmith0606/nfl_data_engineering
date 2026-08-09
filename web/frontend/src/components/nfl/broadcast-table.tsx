'use client';

import * as React from 'react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';
import { cn } from '@/lib/utils';

/**
 * Shared broadcast-styled data table (sketch 003/005 broadcast table chrome
 * — see .claude/skills/sketch-findings-nfl-data-engineering). The yellow
 * condensed-caps header over the 2px mint rule, zebra rows, and mint-wash
 * hover all come from the `.wc-broadcast-table` CSS class
 * (src/styles/broadcast.css) — this component supplies structure and
 * behavior only, it never re-declares that look.
 *
 * Adopted from the two hand-built references (rankings-table, prediction-
 * ledger) that established the pattern: sticky header, frozen identity
 * column with a layered shadow, optional tier bands, optional expand rows,
 * and a `renderCell` escape hatch for mint hero numerals / edge glyphs /
 * range bars.
 *
 * ponytail: a plain styled <table>, not a TanStack wrapper. Every adopter
 * (dynasty/SOS/injury/start-sit/ROS views, multi-compare) is a simple
 * sorted or tiered list. No virtualization — fine under ~1000 rows. No
 * column resize/reorder/visibility toggles — reach for a real table lib
 * (the project already has one under components/ui/table) if that's ever
 * actually needed.
 */

export interface BroadcastColumn<T> {
  /** Unique column key — used as the React key and default header id. */
  key: string;
  header: React.ReactNode;
  /** Numeric columns right-align, text columns left-align. Never 'center'. */
  align?: 'left' | 'right';
  /** Default cell content. */
  accessor: (row: T, rowIndex: number) => React.ReactNode;
  /** Escape hatch — overrides `accessor` for custom rendering (mint hero
   *  numerals via `.wc-num-hero`, edge glyphs via `.wc-edge-glyph`, inline
   *  range bars, badges, etc). Same signature as `accessor` on purpose so
   *  callers can swap one for the other without reshaping anything. */
  renderCell?: (row: T, rowIndex: number) => React.ReactNode;
  /** Tailwind width utility, e.g. 'w-14' or 'min-w-[160px]'. */
  width?: string;
  headerClassName?: string;
  cellClassName?: string;
  /** Marks the frozen identity column (first column, by convention — only
   *  one column should set this). Stays put on horizontal overflow with a
   *  subtle layered shadow separating it from the panning columns. */
  sticky?: boolean;
}

export interface BroadcastTier<T> {
  key: string;
  label: React.ReactNode;
  rows: T[];
  /** Extra classes applied to the band row and its member rows (tint). */
  className?: string;
}

export interface BroadcastTableProps<T> {
  columns: BroadcastColumn<T>[];
  /** Flat row list. Ignored when `tiers` is provided. */
  rows?: T[];
  /** Tier-grouped rows (rankings-table pattern) — a shaded band + condensed
   *  label row spans the table before each tier's members. Grouping/sorting
   *  is the caller's job; this component only renders the bands it's given. */
  tiers?: BroadcastTier<T>[];
  getRowId: (row: T, index: number) => string | number;
  isLoading?: boolean;
  /** Skeleton rows shown while loading — no spinner, no layout shift. */
  skeletonRows?: number;
  emptyMessage?: string;
  /** Persistent "filtered view" indicator shown above the table whenever the
   *  data is scoped (e.g. "QB only", "PHI depth chart"). */
  filteredLabel?: React.ReactNode;
  /** Render-prop for the expanded detail panel. Presence of this prop turns
   *  on the chevron expand/collapse column. */
  renderExpanded?: (row: T) => React.ReactNode;
  rowClassName?: (row: T) => string;
  /** Tailwind min-width utility for the inner <table>, e.g. 'min-w-[760px]'. */
  minWidth?: string;
  className?: string;
}

function alignClass(align: 'left' | 'right' = 'left') {
  return align === 'right' ? 'text-right' : 'text-left';
}

export function BroadcastTable<T>({
  columns,
  rows,
  tiers,
  getRowId,
  isLoading = false,
  skeletonRows = 8,
  emptyMessage = 'No rows match your filters.',
  filteredLabel,
  renderExpanded,
  rowClassName,
  minWidth = 'min-w-[640px]',
  className
}: BroadcastTableProps<T>) {
  const [expanded, setExpanded] = React.useState<Set<string | number>>(
    () => new Set()
  );

  const groups: BroadcastTier<T>[] =
    tiers ?? [{ key: '__flat', label: null, rows: rows ?? [] }];
  const totalRows = groups.reduce((n, g) => n + g.rows.length, 0);
  const colCount = columns.length + (renderExpanded ? 1 : 0);

  function toggle(id: string | number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <Card className={cn('overflow-hidden', className)}>
      {filteredLabel && (
        <div className='wc-display flex items-center gap-[var(--space-2)] border-b px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--fs-xs)] tracking-[0.1em] text-muted-foreground'>
          {filteredLabel}
        </div>
      )}
      <div className='wc-broadcast-table overflow-x-auto'>
        <table
          className={cn(
            'w-full text-[length:var(--fs-sm)] leading-[var(--lh-sm)]',
            minWidth
          )}
        >
          <thead className='bg-muted/50 sticky top-0 z-20'>
            <tr>
              {renderExpanded && (
                <th className='w-8 px-[var(--space-2)] py-[var(--space-3)]' />
              )}
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    'px-[var(--space-3)] py-[var(--space-3)]',
                    alignClass(col.align),
                    col.width,
                    col.sticky &&
                      'bg-muted/50 sticky left-0 z-10 shadow-[4px_0_6px_-4px_rgba(0,0,0,0.5)]',
                    col.headerClassName
                  )}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={i} className='border-b border-border/50'>
                  {renderExpanded && (
                    <td className='px-[var(--space-2)] py-[var(--space-3)]' />
                  )}
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        'px-[var(--space-3)] py-[var(--space-3)]',
                        alignClass(col.align)
                      )}
                    >
                      <Skeleton className='h-[var(--space-4)] w-full max-w-24' />
                    </td>
                  ))}
                </tr>
              ))
            ) : totalRows === 0 ? (
              <tr>
                <td
                  colSpan={colCount}
                  className='px-[var(--space-3)] py-[var(--space-8)] text-center text-muted-foreground'
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              groups.map((group) => (
                <React.Fragment key={group.key}>
                  {group.label != null && (
                    <tr className='border-t-2 border-border'>
                      <td
                        colSpan={colCount}
                        className={cn(
                          'px-[var(--space-3)] py-[var(--space-2)]',
                          group.className
                        )}
                      >
                        <span className='wc-display text-[length:var(--fs-xs)] tracking-[0.12em] text-muted-foreground'>
                          {group.label}
                        </span>
                      </td>
                    </tr>
                  )}
                  {group.rows.map((row, idx) => {
                    const id = getRowId(row, idx);
                    const isOpen = expanded.has(id);
                    return (
                      <React.Fragment key={id}>
                        <tr
                          className={cn(
                            'border-b border-border/50 transition-transform duration-150 ease-out hover:-translate-y-px',
                            group.className,
                            rowClassName?.(row)
                          )}
                        >
                          {renderExpanded && (
                            <td className='px-[var(--space-2)] py-[var(--space-3)]'>
                              <button
                                type='button'
                                onClick={() => toggle(id)}
                                aria-label={isOpen ? 'Collapse row' : 'Expand row'}
                                aria-expanded={isOpen}
                                className='text-muted-foreground hover:text-foreground transition-colors'
                              >
                                <Icons.chevronRight
                                  className={cn(
                                    'size-[var(--space-4)] transition-transform duration-150',
                                    isOpen && 'rotate-90'
                                  )}
                                />
                              </button>
                            </td>
                          )}
                          {columns.map((col) => (
                            <td
                              key={col.key}
                              className={cn(
                                'px-[var(--space-3)] py-[var(--space-3)]',
                                alignClass(col.align),
                                col.sticky &&
                                  cn(
                                    'sticky left-0 z-[1] shadow-[4px_0_6px_-4px_rgba(0,0,0,0.5)]',
                                    group.className || 'bg-background'
                                  ),
                                col.cellClassName
                              )}
                            >
                              {(col.renderCell ?? col.accessor)(row, idx)}
                            </td>
                          ))}
                        </tr>
                        {renderExpanded && isOpen && (
                          <tr className='border-b border-border/50'>
                            <td
                              colSpan={colCount}
                              className='bg-muted/20 px-[var(--space-3)] py-[var(--space-3)]'
                            >
                              {renderExpanded(row)}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
