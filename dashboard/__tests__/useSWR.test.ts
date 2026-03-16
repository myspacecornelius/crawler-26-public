/**
 * Tests for the custom SWR data-fetching hook.
 */
import { renderHook, waitFor, act } from '@testing-library/react';
import { useSWRFetch } from '@/lib/hooks/useSWR';

// Mock timers for dedup/refresh tests
beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

describe('useSWRFetch', () => {
  it('fetches data and sets loading states correctly', async () => {
    jest.useRealTimers();
    const fetcher = jest.fn().mockResolvedValue({ count: 42 });

    const { result } = renderHook(() =>
      useSWRFetch('test-key-1', fetcher),
    );

    // Initially loading
    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
    expect(result.current.error).toBeUndefined();

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual({ count: 42 });
    expect(result.current.error).toBeUndefined();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('returns fallback data while loading', async () => {
    jest.useRealTimers();
    const fetcher = jest.fn().mockResolvedValue({ count: 10 });
    const fallback = { count: 0 };

    const { result } = renderHook(() =>
      useSWRFetch('test-key-2', fetcher, { fallbackData: fallback }),
    );

    // Should have fallback data immediately
    expect(result.current.data).toEqual(fallback);
    expect(result.current.isLoading).toBe(false); // Not loading because data exists

    await waitFor(() => {
      expect(result.current.data).toEqual({ count: 10 });
    });
  });

  it('handles errors gracefully', async () => {
    jest.useRealTimers();
    const fetcher = jest.fn().mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() =>
      useSWRFetch('test-key-3', fetcher),
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('Network error');
    expect(result.current.data).toBeUndefined();
  });

  it('does not fetch when key is null', () => {
    const fetcher = jest.fn().mockResolvedValue({ data: true });

    renderHook(() => useSWRFetch(null, fetcher));

    expect(fetcher).not.toHaveBeenCalled();
  });

  it('does not fetch when enabled is false', () => {
    const fetcher = jest.fn().mockResolvedValue({ data: true });

    renderHook(() =>
      useSWRFetch('test-key-4', fetcher, { enabled: false }),
    );

    expect(fetcher).not.toHaveBeenCalled();
  });

  it('mutate can update data optimistically', async () => {
    jest.useRealTimers();
    const fetcher = jest.fn().mockResolvedValue({ count: 1 });

    const { result } = renderHook(() =>
      useSWRFetch('test-key-5', fetcher),
    );

    await waitFor(() => {
      expect(result.current.data).toEqual({ count: 1 });
    });

    // Update optimistically
    await act(async () => {
      await result.current.mutate({ count: 99 });
    });

    expect(result.current.data).toEqual({ count: 99 });
  });

  it('mutate with function updater', async () => {
    jest.useRealTimers();
    const fetcher = jest.fn().mockResolvedValue({ count: 5 });

    const { result } = renderHook(() =>
      useSWRFetch('test-key-6', fetcher),
    );

    await waitFor(() => {
      expect(result.current.data).toEqual({ count: 5 });
    });

    await act(async () => {
      await result.current.mutate((current) => ({
        count: (current?.count ?? 0) + 1,
      }));
    });

    expect(result.current.data).toEqual({ count: 6 });
  });
});
