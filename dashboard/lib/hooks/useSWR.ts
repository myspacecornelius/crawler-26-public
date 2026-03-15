'use client';

import { useEffect, useState, useCallback, useRef } from 'react';

export interface SWROptions<T> {
  /** Revalidation interval in milliseconds (0 = disabled) */
  refreshInterval?: number;
  /** Fallback data to use before first fetch */
  fallbackData?: T;
  /** Whether to revalidate on window focus */
  revalidateOnFocus?: boolean;
  /** Whether to deduplicate requests */
  dedupingInterval?: number;
  /** Whether the hook should fetch at all */
  enabled?: boolean;
}

export interface SWRResponse<T> {
  data: T | undefined;
  error: Error | undefined;
  isLoading: boolean;
  isValidating: boolean;
  mutate: (data?: T | Promise<T> | ((current?: T) => T)) => Promise<void>;
}

// Simple global cache
const cache = new Map<string, { data: unknown; timestamp: number }>();
const DEDUP_INTERVAL = 2000;

export function useSWRFetch<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  options: SWROptions<T> = {},
): SWRResponse<T> {
  const {
    refreshInterval = 0,
    fallbackData,
    revalidateOnFocus = true,
    dedupingInterval = DEDUP_INTERVAL,
    enabled = true,
  } = options;

  const [data, setData] = useState<T | undefined>(() => {
    if (key && cache.has(key)) return cache.get(key)!.data as T;
    return fallbackData;
  });
  const [error, setError] = useState<Error | undefined>();
  const [isLoading, setIsLoading] = useState(!data);
  const [isValidating, setIsValidating] = useState(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const mutate = useCallback(
    async (newData?: T | Promise<T> | ((current?: T) => T)) => {
      if (newData === undefined) {
        // Revalidate
        setIsValidating(true);
        try {
          const result = await fetcherRef.current();
          setData(result);
          if (key) cache.set(key, { data: result, timestamp: Date.now() });
          setError(undefined);
        } catch (e) {
          setError(e instanceof Error ? e : new Error(String(e)));
        } finally {
          setIsValidating(false);
        }
        return;
      }

      if (typeof newData === 'function') {
        const fn = newData as (current?: T) => T;
        const result = fn(data);
        setData(result);
        if (key) cache.set(key, { data: result, timestamp: Date.now() });
      } else if (newData instanceof Promise) {
        const result = await newData;
        setData(result);
        if (key) cache.set(key, { data: result, timestamp: Date.now() });
      } else {
        setData(newData);
        if (key) cache.set(key, { data: newData, timestamp: Date.now() });
      }
    },
    [key, data],
  );

  useEffect(() => {
    if (!key || !enabled) return;

    // Check dedup
    const cached = cache.get(key);
    if (cached && Date.now() - cached.timestamp < dedupingInterval) {
      setData(cached.data as T);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(!data);
    setIsValidating(true);

    fetcherRef.current()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        cache.set(key, { data: result, timestamp: Date.now() });
        setError(undefined);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e : new Error(String(e)));
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
        setIsValidating(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  // Refresh interval
  useEffect(() => {
    if (!key || !enabled || refreshInterval <= 0) return;
    const id = setInterval(() => mutate(), refreshInterval);
    return () => clearInterval(id);
  }, [key, enabled, refreshInterval, mutate]);

  // Focus revalidation
  useEffect(() => {
    if (!key || !enabled || !revalidateOnFocus) return;
    const handler = () => mutate();
    window.addEventListener('focus', handler);
    return () => window.removeEventListener('focus', handler);
  }, [key, enabled, revalidateOnFocus, mutate]);

  return { data, error, isLoading, isValidating, mutate };
}
