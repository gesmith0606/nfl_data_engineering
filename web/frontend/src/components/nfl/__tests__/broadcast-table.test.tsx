/**
 * Unit tests for the shared <BroadcastTable /> primitive.
 *
 * Covers the contract the six adopter views (dynasty/SOS/injury/start-sit/
 * ROS, multi-compare) rely on: column alignment, loading skeletons with no
 * spinner, the empty state, tier band grouping, the frozen identity column,
 * the filtered-view indicator slot, and the expand/collapse render-prop.
 *
 * Also covers the opt-in density toggle (`densityKey`) and column-visibility
 * popover (`hideableColumns`) — both must be strictly additive: a table
 * rendered with none of the new props must produce byte-identical markup to
 * the pre-existing contract (see the "no-props regression" block below).
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';

/** Direct in-memory localStorage mock — deterministic, no reliance on jsdom's
 *  real Storage implementation, and lets tests assert exact setItem calls. */
function installLocalStorageMock() {
  const store = new Map<string, string>();
  const mock = {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value);
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key);
    }),
    clear: vi.fn(() => store.clear())
  };
  Object.defineProperty(window, 'localStorage', { value: mock, configurable: true });
  return mock;
}

interface Row {
  id: string;
  name: string;
  points: number;
}

const columns: BroadcastColumn<Row>[] = [
  { key: 'name', header: 'Player', sticky: true, accessor: (r) => r.name },
  { key: 'points', header: 'Points', align: 'right', accessor: (r) => r.points.toFixed(1) }
];

const rows: Row[] = [
  { id: 'a', name: 'Alpha', points: 12.3 },
  { id: 'b', name: 'Bravo', points: 9.1 }
];

describe('BroadcastTable', () => {
  it('renders rows via column accessors', () => {
    render(<BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} />);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('12.3')).toBeInTheDocument();
  });

  it('right-aligns numeric columns and left-aligns text columns', () => {
    render(<BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} />);
    const headerRow = screen.getAllByRole('columnheader');
    expect(headerRow[0]).toHaveClass('text-left');
    expect(headerRow[1]).toHaveClass('text-right');
  });

  it('shows skeleton rows (no spinner) while loading', () => {
    const { container } = render(
      <BroadcastTable columns={columns} rows={[]} getRowId={(r) => r.id} isLoading skeletonRows={3} />
    );
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(container.querySelector('svg.animate-spin')).toBeNull();
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
  });

  it('renders the empty message when there are no rows and not loading', () => {
    render(
      <BroadcastTable
        columns={columns}
        rows={[]}
        getRowId={(r) => r.id}
        emptyMessage='Nothing to show'
      />
    );
    expect(screen.getByText('Nothing to show')).toBeInTheDocument();
  });

  it('renders tier bands with their label and member rows', () => {
    render(
      <BroadcastTable
        columns={columns}
        tiers={[
          { key: 'elite', label: 'Elite', rows: [rows[0]] },
          { key: 'bench', label: 'Bench', rows: [rows[1]] }
        ]}
        getRowId={(r) => r.id}
      />
    );
    expect(screen.getByText('Elite')).toBeInTheDocument();
    expect(screen.getByText('Bench')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Bravo')).toBeInTheDocument();
  });

  it('shows the filtered-view indicator only when provided', () => {
    const { rerender } = render(
      <BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} />
    );
    expect(screen.queryByText('QB only')).not.toBeInTheDocument();

    rerender(
      <BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} filteredLabel='QB only' />
    );
    expect(screen.getByText('QB only')).toBeInTheDocument();
  });

  it('marks the sticky column as frozen with a layered shadow', () => {
    render(<BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} />);
    const headerRow = screen.getAllByRole('columnheader');
    expect(headerRow[0].className).toMatch(/sticky/);
    expect(headerRow[0].className).toMatch(/shadow-/);
  });

  it('expands and collapses a row via the chevron toggle', () => {
    render(
      <BroadcastTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        renderExpanded={(r) => <div>Detail for {r.name}</div>}
      />
    );
    expect(screen.queryByText('Detail for Alpha')).not.toBeInTheDocument();

    const toggles = screen.getAllByRole('button', { name: 'Expand row' });
    fireEvent.click(toggles[0]);
    expect(screen.getByText('Detail for Alpha')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Collapse row' }));
    expect(screen.queryByText('Detail for Alpha')).not.toBeInTheDocument();
  });

  it('lets renderCell override the default accessor content', () => {
    const withOverride: BroadcastColumn<Row>[] = [
      columns[0],
      {
        ...columns[1],
        renderCell: (r) => <span className='wc-num-hero'>{r.points.toFixed(0)}</span>
      }
    ];
    render(<BroadcastTable columns={withOverride} rows={rows} getRowId={(r) => r.id} />);
    const hero = screen.getByText('12');
    expect(hero).toHaveClass('wc-num-hero');
    expect(screen.queryByText('12.3')).not.toBeInTheDocument();
  });

  it('supports table semantics for the header row', () => {
    render(<BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} />);
    expect(within(screen.getByRole('table')).getAllByRole('row').length).toBeGreaterThan(0);
  });

  // ---------------------------------------------------------------------
  // Backward-compat proof: zero `densityKey`/`hideableColumns` props must
  // produce the exact same markup as before those props existed.
  // ---------------------------------------------------------------------
  it('renders no toolbar and the original wrapper class when no new props are passed', () => {
    const { container } = render(
      <BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} />
    );
    expect(screen.queryByRole('group', { name: 'Row density' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Columns' })).not.toBeInTheDocument();
    const wrapper = container.querySelector('.wc-broadcast-table');
    expect(wrapper).not.toBeNull();
    expect(wrapper?.className).toBe('wc-broadcast-table overflow-x-auto');
  });
});

describe('BroadcastTable — row density (densityKey)', () => {
  beforeEach(() => {
    installLocalStorageMock();
  });

  it('does not render the density toggle when densityKey is omitted', () => {
    render(<BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} />);
    expect(screen.queryByRole('group', { name: 'Row density' })).not.toBeInTheDocument();
  });

  it('renders a three-state segmented control defaulting to comfortable', () => {
    render(
      <BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} densityKey='test:density' />
    );
    const group = screen.getByRole('group', { name: 'Row density' });
    expect(within(group).getByText('Compact')).toBeInTheDocument();
    expect(within(group).getByText('Comfortable')).toBeInTheDocument();
    expect(within(group).getByText('Spacious')).toBeInTheDocument();
    expect(within(group).getByText('Comfortable')).toHaveAttribute('aria-pressed', 'true');
  });

  it('applies the density class to the table wrapper and persists the choice', () => {
    const storage = installLocalStorageMock();
    const { container } = render(
      <BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} densityKey='test:density' />
    );
    fireEvent.click(screen.getByText('Compact'));

    const wrapper = container.querySelector('.wc-broadcast-table');
    expect(wrapper).toHaveClass('wc-density-compact');
    expect(storage.setItem).toHaveBeenCalledWith(
      'wc-broadcast-table:test:density',
      expect.stringContaining('"density":"compact"')
    );
  });

  it('comfortable renders with exactly the original wrapper classes (no density class added)', () => {
    const { container } = render(
      <BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} densityKey='test:density' />
    );
    const wrapper = container.querySelector('.wc-broadcast-table');
    expect(wrapper?.className).toBe('wc-broadcast-table overflow-x-auto');
  });

  it('hydrates a persisted density choice on mount (SSR-safe, client-only read)', () => {
    const storage = installLocalStorageMock();
    storage.setItem('wc-broadcast-table:test:density', JSON.stringify({ density: 'spacious' }));
    const { container } = render(
      <BroadcastTable columns={columns} rows={rows} getRowId={(r) => r.id} densityKey='test:density' />
    );
    const wrapper = container.querySelector('.wc-broadcast-table');
    expect(wrapper).toHaveClass('wc-density-spacious');
    expect(screen.getByText('Spacious')).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('BroadcastTable — column visibility (hideableColumns)', () => {
  const wideColumns: BroadcastColumn<Row>[] = [
    ...columns,
    { key: 'extra', header: 'Extra', accessor: () => 'x' }
  ];

  beforeAll(() => {
    // Radix DropdownMenu needs these in jsdom (no real layout/pointer capture
    // support) — same polyfill used by mock-draft-setup-dialog.test.tsx.
    window.HTMLElement.prototype.hasPointerCapture = () => false;
    window.HTMLElement.prototype.scrollIntoView = () => {};
    window.HTMLElement.prototype.releasePointerCapture = () => {};
  });

  beforeEach(() => {
    installLocalStorageMock();
  });

  // Radix's menu trigger opens on `pointerdown` (press), not `click` — see
  // @radix-ui/react-dropdown-menu's DropdownMenuTrigger. Item selection
  // itself does fire on `click`, so only the open action needs this.
  function openColumnsMenu() {
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Columns' }), {
      button: 0,
      ctrlKey: false
    });
  }

  it('does not render the Columns popover when hideableColumns is omitted', () => {
    render(<BroadcastTable columns={wideColumns} rows={rows} getRowId={(r) => r.id} />);
    expect(screen.queryByRole('button', { name: 'Columns' })).not.toBeInTheDocument();
  });

  it('hides a column via the popover checkbox', () => {
    render(
      <BroadcastTable
        columns={wideColumns}
        rows={rows}
        getRowId={(r) => r.id}
        hideableColumns={['extra']}
      />
    );
    expect(screen.getByText('Extra')).toBeInTheDocument();

    openColumnsMenu();
    const checkbox = screen.getByRole('menuitemcheckbox', { name: 'Extra' });
    expect(checkbox).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(checkbox);

    expect(screen.queryByText('Extra')).not.toBeInTheDocument();
    // The always-visible columns remain.
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('12.3')).toBeInTheDocument();
  });

  it('never lets the sticky identity column be hidden, even if listed', () => {
    render(
      <BroadcastTable
        columns={wideColumns}
        rows={rows}
        getRowId={(r) => r.id}
        hideableColumns={['name', 'extra']}
      />
    );
    openColumnsMenu();
    expect(screen.queryByRole('menuitemcheckbox', { name: 'Player' })).not.toBeInTheDocument();
    expect(screen.getByRole('menuitemcheckbox', { name: 'Extra' })).toBeInTheDocument();
    // Sticky column header/cells stay rendered regardless.
    expect(screen.getAllByText('Alpha').length).toBeGreaterThan(0);
  });

  it('persists hidden-column choices alongside density under the same storage key', () => {
    const storage = installLocalStorageMock();
    render(
      <BroadcastTable
        columns={wideColumns}
        rows={rows}
        getRowId={(r) => r.id}
        densityKey='test:cols'
        hideableColumns={['extra']}
      />
    );
    openColumnsMenu();
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Extra' }));

    expect(storage.setItem).toHaveBeenCalledWith(
      'wc-broadcast-table:test:cols',
      expect.stringContaining('"hiddenColumns":["extra"]')
    );
  });
});
