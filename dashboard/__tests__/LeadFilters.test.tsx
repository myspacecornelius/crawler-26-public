/**
 * Tests for the LeadFilters component.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import LeadFilters, { useLeadFilters } from '@/components/LeadFilters';
import { renderHook, act } from '@testing-library/react';

describe('LeadFilters', () => {
  const defaultFilters = {
    search: '',
    tier: '',
    min_score: '',
    has_email: '',
    email_status: '',
    fund: '',
    sector: '',
    stage: '',
    hq: '',
    sort_by: 'score',
    sort_dir: 'desc',
  };

  it('renders search input', () => {
    render(<LeadFilters filters={defaultFilters} onChange={jest.fn()} />);

    const searchInput = screen.getByLabelText('Search leads');
    expect(searchInput).toBeInTheDocument();
  });

  it('calls onChange when search text is entered', () => {
    const onChange = jest.fn();
    render(<LeadFilters filters={defaultFilters} onChange={onChange} />);

    const searchInput = screen.getByLabelText('Search leads');
    fireEvent.change(searchInput, { target: { value: 'test query' } });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ search: 'test query' }),
    );
  });

  it('toggles filter panel visibility', () => {
    render(<LeadFilters filters={defaultFilters} onChange={jest.fn()} />);

    // Panel should not be visible
    expect(screen.queryByRole('region', { name: 'Lead filters' })).not.toBeInTheDocument();

    // Click filters button
    fireEvent.click(screen.getByText('Filters'));

    // Panel should now be visible
    expect(screen.getByRole('region', { name: 'Lead filters' })).toBeInTheDocument();
  });

  it('displays sort controls', () => {
    render(<LeadFilters filters={defaultFilters} onChange={jest.fn()} />);

    const sortSelect = screen.getByLabelText('Sort by');
    expect(sortSelect).toBeInTheDocument();
    expect(sortSelect).toHaveValue('score');
  });

  it('toggles sort direction', () => {
    const onChange = jest.fn();
    render(<LeadFilters filters={defaultFilters} onChange={onChange} />);

    const dirButton = screen.getByLabelText('Sort ascending');
    fireEvent.click(dirButton);

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ sort_dir: 'asc' }),
    );
  });

  it('shows active filter count', () => {
    const filtersWithActive = {
      ...defaultFilters,
      tier: 'HOT',
      fund: 'Sequoia',
    };
    render(<LeadFilters filters={filtersWithActive} onChange={jest.fn()} />);

    // Should show badge with count 2
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows clear all button when filters are active', () => {
    const filtersWithActive = {
      ...defaultFilters,
      tier: 'HOT',
    };
    const onChange = jest.fn();

    render(<LeadFilters filters={filtersWithActive} onChange={onChange} />);

    // Open filter panel
    fireEvent.click(screen.getByText('Filters'));

    // Clear all button should be present
    fireEvent.click(screen.getByText('Clear all filters'));

    expect(onChange).toHaveBeenCalledWith(defaultFilters);
  });

  it('shows total results count when provided', () => {
    const filtersWithActive = { ...defaultFilters, tier: 'HOT' };
    render(
      <LeadFilters filters={filtersWithActive} onChange={jest.fn()} totalResults={1234} />,
    );

    // Open filter panel
    fireEvent.click(screen.getByText('Filters'));

    expect(screen.getByText('1,234 results')).toBeInTheDocument();
  });
});

describe('useLeadFilters hook', () => {
  it('initializes with default values', () => {
    const { result } = renderHook(() => useLeadFilters());

    expect(result.current.filters.search).toBe('');
    expect(result.current.filters.sort_by).toBe('score');
    expect(result.current.activeCount).toBe(0);
  });

  it('updates individual filter', () => {
    const { result } = renderHook(() => useLeadFilters());

    act(() => {
      result.current.updateFilter('tier', 'HOT');
    });

    expect(result.current.filters.tier).toBe('HOT');
    expect(result.current.activeCount).toBe(1);
  });

  it('clears all filters', () => {
    const { result } = renderHook(() => useLeadFilters());

    act(() => {
      result.current.updateFilter('tier', 'HOT');
      result.current.updateFilter('fund', 'Sequoia');
    });

    expect(result.current.activeCount).toBe(2);

    act(() => {
      result.current.clearAll();
    });

    expect(result.current.activeCount).toBe(0);
    expect(result.current.filters.tier).toBe('');
    expect(result.current.filters.fund).toBe('');
  });

  it('converts filters to URL params', () => {
    const { result } = renderHook(() => useLeadFilters());

    act(() => {
      result.current.updateFilter('tier', 'HOT');
      result.current.updateFilter('min_score', '80');
    });

    const params = result.current.toParams();
    expect(params.tier).toBe('HOT');
    expect(params.min_score).toBe('80');
    expect(params.sort_by).toBe('score');
    // Empty values should not be included
    expect(params.fund).toBeUndefined();
  });
});
