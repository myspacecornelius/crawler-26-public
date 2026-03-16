/**
 * Tests for the ErrorView component.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorView from '@/components/ui/ErrorView';

describe('ErrorView', () => {
  it('renders with default title and message', () => {
    render(<ErrorView />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('An unexpected error occurred. Please try again.')).toBeInTheDocument();
  });

  it('renders with custom title and message', () => {
    render(<ErrorView title="Not found" message="The requested resource was not found." />);

    expect(screen.getByText('Not found')).toBeInTheDocument();
    expect(screen.getByText('The requested resource was not found.')).toBeInTheDocument();
  });

  it('has role="alert" for screen readers', () => {
    render(<ErrorView />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('shows retry button when onRetry is provided', () => {
    const onRetry = jest.fn();
    render(<ErrorView onRetry={onRetry} />);

    const retryButton = screen.getByText('Try again');
    expect(retryButton).toBeInTheDocument();

    fireEvent.click(retryButton);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('does not show retry button when onRetry is not provided', () => {
    render(<ErrorView />);

    expect(screen.queryByText('Try again')).not.toBeInTheDocument();
  });
});
