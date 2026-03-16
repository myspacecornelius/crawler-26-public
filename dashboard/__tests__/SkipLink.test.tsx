/**
 * Tests for the SkipLink accessibility component.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import SkipLink from '@/components/ui/SkipLink';

describe('SkipLink', () => {
  it('renders with correct href', () => {
    render(<SkipLink />);

    const link = screen.getByText('Skip to main content');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '#main-content');
  });

  it('uses custom target ID', () => {
    render(<SkipLink targetId="custom-content" />);

    const link = screen.getByText('Skip to main content');
    expect(link).toHaveAttribute('href', '#custom-content');
  });

  it('is visually hidden by default (sr-only class)', () => {
    render(<SkipLink />);

    const link = screen.getByText('Skip to main content');
    expect(link.className).toContain('sr-only');
  });
});
