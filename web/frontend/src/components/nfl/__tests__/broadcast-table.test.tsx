/**
 * Unit tests for the shared <BroadcastTable /> primitive.
 *
 * Covers the contract the six adopter views (dynasty/SOS/injury/start-sit/
 * ROS, multi-compare) rely on: column alignment, loading skeletons with no
 * spinner, the empty state, tier band grouping, the frozen identity column,
 * the filtered-view indicator slot, and the expand/collapse render-prop.
 */
import { describe, it, expect } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { BroadcastTable, type BroadcastColumn } from '@/components/nfl/broadcast-table';

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
});
