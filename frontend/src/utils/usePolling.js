// Ask again every few seconds while something works in the background (a
// Q&A analysis, a report), so the page shows progress without a reload.

import { useEffect } from 'react';

// Call `load` every `everyMs` while `active` is true; stop when the page closes.
export function usePolling(load, active, everyMs = 3000) {
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(load, everyMs);
    return () => clearInterval(timer);
  }, [load, active, everyMs]);
}
