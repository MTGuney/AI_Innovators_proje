import { useEffect, useState } from 'react';

/**
 * Delay a rapidly-changing value. Typing in a search box should not fire one
 * request per keystroke against the reports endpoint.
 */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
