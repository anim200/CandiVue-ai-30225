// Time helpers for the interview: the call timer and "starts in …".

import { useEffect, useState } from 'react';

// "4:29:44" (with hours) or "12:05" (under an hour).
export function formatElapsed(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const pad = (n) => String(n).padStart(2, '0');
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

// How far past the planned length: "+12 min over", "+26 h 57 min over".
export function overText(minutes) {
  const m = Math.floor(minutes);
  if (m < 60) return `+${m} min over`;
  return `+${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min over`;
}

// "in 2 days", "in 3 h 05 min", "in 4 min", or null when the time has come.
export function startsIn(iso, now = Date.now()) {
  const minutes = Math.round((new Date(iso) - now) / 60000);
  if (minutes <= 0) return null;
  if (minutes >= 48 * 60) return `in ${Math.round(minutes / (24 * 60))} days`;
  if (minutes >= 60) return `in ${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`;
  return `in ${minutes} min`;
}

// The current time, updated every `everyMs` (re-renders the caller).
export function useNow(everyMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(timer);
  }, [everyMs]);
  return now;
}

// Seconds since `startIso` (or since the page opened when the server has no
// start time yet).
export function useElapsed(startIso) {
  const [opened] = useState(() => Date.now());
  const now = useNow();
  const start = startIso ? new Date(startIso).getTime() : opened;
  return (now - start) / 1000;
}
