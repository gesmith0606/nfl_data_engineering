'use client';

import * as React from 'react';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Icons } from '@/components/icons';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
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
 * sorted or tiered list. No virtualization — fine under ~1000 rows. Optional
 * `densityKey`/`hideableColumns` add a persisted density toggle + show/hide
 * popover (see below); still no column resize/reorder — reach for a real
 * table lib (the project already has one under components/ui/table) if that's
 * ever actually needed.
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

/** Three-state row density (UX research: persist density as a user setting
 *  rather than a fixed choice). `comfortable` renders identically to the
 *  table's pre-density-toggle padding — the backward-compat baseline. */
export type BroadcastTableDensity = 'compact' | 'comfortable' | 'spacious';

const DENSITY_VALUES: BroadcastTableDensity[] = ['compact', 'comfortable', 'spacious'];
const DENSITY_LABEL: Record<BroadcastTableDensity, string> = {
  compact: 'Compact',
  comfortable: 'Comfortable',
  spacious: 'Spacious'
};

interface BroadcastTablePrefs {
  density?: BroadcastTableDensity;
  hiddenColumns?: string[];
}

/** localStorage key namespace for `densityKey`. Density and hidden-column
 *  choices are stored together as one JSON blob per key:
 *  `{ density?: 'compact'|'comfortable'|'spacious', hiddenColumns?: string[] }`. */
function prefsStorageKey(densityKey: string): string {
  return `wc-broadcast-table:${densityKey}`;
}

function readPrefs(densityKey: string): BroadcastTablePrefs | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(prefsStorageKey(densityKey));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === 'object' ? (parsed as BroadcastTablePrefs) : null;
  } catch {
    // Corrupt JSON / quota / private-mode denial — fall back to defaults silently.
    return null;
  }
}

function writePrefs(densityKey: string, prefs: BroadcastTablePrefs): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(prefsStorageKey(densityKey), JSON.stringify(prefs));
  } catch {
    // Quota / private-mode — the choice just won't persist this session.
  }
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
  /** Opt-in — renders a persisted row-density toggle (compact/comfortable/
   *  spacious) in a toolbar row above the table, and, when `hideableColumns`
   *  is also set, the "Columns" show/hide popover in the same row. The choice
   *  is stored client-side in localStorage under `wc-broadcast-table:${densityKey}`.
   *  Omit to render the table exactly as before, with no toolbar. */
  densityKey?: string;
  /** Column keys the user may hide via the "Columns" popover. Works without
   *  `densityKey` (session-only state); persists across reloads only when
   *  `densityKey` is also provided, since both prefs share one storage entry.
   *  A sticky (frozen identity) column is never hideable, even if its key is
   *  listed here — enforced defensively.
   *  ponytail: no drag-reorder, no column resize — reach for a real table lib
   *  (components/ui/table) if that's ever actually needed. */
  hideableColumns?: string[];
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
  className,
  densityKey,
  hideableColumns
}: BroadcastTableProps<T>) {
  const [expanded, setExpanded] = React.useState<Set<string | number>>(
    () => new Set()
  );
  const [density, setDensity] = React.useState<BroadcastTableDensity>('comfortable');
  const [hiddenColumns, setHiddenColumns] = React.useState<Set<string>>(() => new Set());

  // Hydrate persisted prefs client-side only, after the first render — the
  // SSR/first-paint markup always matches the defaults above, so there's no
  // hydration mismatch (same pattern as use-persistent-chat.ts).
  React.useEffect(() => {
    if (!densityKey) return;
    const stored = readPrefs(densityKey);
    if (!stored) return;
    if (stored.density && DENSITY_VALUES.includes(stored.density)) {
      setDensity(stored.density);
    }
    if (stored.hiddenColumns) {
      setHiddenColumns(new Set(stored.hiddenColumns));
    }
    // densityKey is expected to stay stable for a mounted table instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sticky (frozen identity) column can never be hideable, even if the
  // caller lists its key by mistake.
  const hideableSet = React.useMemo(() => {
    const stickyKeys = new Set(columns.filter((c) => c.sticky).map((c) => c.key));
    return new Set((hideableColumns ?? []).filter((k) => !stickyKeys.has(k)));
  }, [columns, hideableColumns]);

  const visibleColumns =
    hideableSet.size > 0
      ? columns.filter((c) => !(hiddenColumns.has(c.key) && hideableSet.has(c.key)))
      : columns;

  function handleDensityChange(next: BroadcastTableDensity) {
    setDensity(next);
    if (densityKey) {
      writePrefs(densityKey, { density: next, hiddenColumns: Array.from(hiddenColumns) });
    }
  }

  function toggleColumn(key: string) {
    setHiddenColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      if (densityKey) {
        writePrefs(densityKey, { density, hiddenColumns: Array.from(next) });
      }
      return next;
    });
  }

  const groups: BroadcastTier<T>[] =
    tiers ?? [{ key: '__flat', label: null, rows: rows ?? [] }];
  const totalRows = groups.reduce((n, g) => n + g.rows.length, 0);
  const colCount = visibleColumns.length + (renderExpanded ? 1 : 0);
  const densityClass =
    density === 'compact'
      ? 'wc-density-compact'
      : density === 'spacious'
        ? 'wc-density-spacious'
        : undefined;

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
      {(densityKey || hideableSet.size > 0) && (
        <div className='wc-display flex items-center justify-end gap-[var(--space-2)] border-b px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--fs-xs)]'>
          {densityKey && (
            <div
              role='group'
              aria-label='Row density'
              className='flex items-center gap-0.5 rounded-full border border-border/60 p-0.5'
            >
              {DENSITY_VALUES.map((d) => (
                <button
                  key={d}
                  type='button'
                  onClick={() => handleDensityChange(d)}
                  aria-pressed={density === d}
                  className={cn(
                    'rounded-full px-2 py-1 text-[10px] tracking-[0.08em] uppercase transition-colors',
                    density === d
                      ? 'bg-[var(--wc-mint,#91edd0)] text-[var(--wc-mint-ink,#04140e)]'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                >
                  {DENSITY_LABEL[d]}
                </button>
              ))}
            </div>
          )}
          {hideableSet.size > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type='button'
                  aria-label='Columns'
                  className='flex items-center gap-1 rounded-full border border-border/60 px-2 py-1 text-[10px] tracking-[0.08em] text-muted-foreground uppercase transition-colors hover:text-foreground'
                >
                  <Icons.table className='size-3.5' />
                  Columns
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align='end' className='bg-popover'>
                {columns
                  .filter((c) => hideableSet.has(c.key))
                  .map((c) => (
                    <DropdownMenuCheckboxItem
                      key={c.key}
                      checked={!hiddenColumns.has(c.key)}
                      onCheckedChange={() => toggleColumn(c.key)}
                    >
                      {typeof c.header === 'string' ? c.header : c.key}
                    </DropdownMenuCheckboxItem>
                  ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      )}
      {filteredLabel && (
        <div className='wc-display flex items-center gap-[var(--space-2)] border-b px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--fs-xs)] tracking-[0.1em] text-muted-foreground'>
          {filteredLabel}
        </div>
      )}
      <div className={cn('wc-broadcast-table overflow-x-auto', densityClass)}>
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
              {visibleColumns.map((col) => (
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
                  {visibleColumns.map((col) => (
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
                          {visibleColumns.map((col) => (
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
