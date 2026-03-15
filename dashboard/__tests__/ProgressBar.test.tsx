/**
 * Tests for the ProgressBar UI component.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import ProgressBar from '@/components/ui/ProgressBar';

describe('ProgressBar', () => {
  it('renders with correct aria attributes', () => {
    render(<ProgressBar value={50} max={100} label="Credits used" />);

    const progressbar = screen.getByRole('progressbar');
    expect(progressbar).toBeInTheDocument();
    expect(progressbar).toHaveAttribute('aria-valuenow', '50');
    expect(progressbar).toHaveAttribute('aria-valuemin', '0');
    expect(progressbar).toHaveAttribute('aria-valuemax', '100');
    expect(progressbar).toHaveAttribute('aria-label', 'Credits used');
  });

  it('displays label text', () => {
    render(<ProgressBar value={30} label="Upload progress" />);

    expect(screen.getByText('Upload progress')).toBeInTheDocument();
  });

  it('shows percentage when enabled', () => {
    render(<ProgressBar value={75} showPercentage />);

    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('clamps value between 0 and 100', () => {
    render(<ProgressBar value={150} max={100} />);

    const progressbar = screen.getByRole('progressbar');
    expect(progressbar).toHaveAttribute('aria-valuenow', '100');
  });

  it('handles zero max gracefully', () => {
    // value/max = 0/0, should not crash
    render(<ProgressBar value={0} max={0} />);

    const progressbar = screen.getByRole('progressbar');
    expect(progressbar).toBeInTheDocument();
  });

  it('applies variant classes', () => {
    const { container } = render(<ProgressBar value={50} variant="success" />);

    // The fill div should have the success color class
    const fill = container.querySelector('.bg-emerald-500');
    expect(fill).toBeInTheDocument();
  });

  it('renders different sizes', () => {
    const { container: smContainer } = render(<ProgressBar value={50} size="sm" />);
    const { container: lgContainer } = render(<ProgressBar value={50} size="lg" />);

    expect(smContainer.querySelector('.h-1\\.5')).toBeInTheDocument();
    expect(lgContainer.querySelector('.h-4')).toBeInTheDocument();
  });
});
