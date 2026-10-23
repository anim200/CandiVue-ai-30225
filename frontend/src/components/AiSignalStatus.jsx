// The "Signal" status shown while the AI works: the small CandiVue match
// mark (candidate dots travel to the centre, which pulses), the current
// step (the new one slides up, the old one slides out) and the time since
// the work started ("4s", "1m 05s").
//
// status: the real step, when the backend reports one (e.g. "Screening CV
// 3 of 5…"). Otherwise steps: shown one after another every stepMs, then
// the last one stays until the answer arrives. startedAt: when the work
// started (ISO text or ms; default: when this appears). markSize: 22px, or
// 28px in the chat, where the mark takes the assistant avatar's place.

import { useEffect, useRef, useState } from 'react';

import { formatElapsed, stepAt } from './aiSignal';
import AssistantMark from './AssistantMark';
import classes from './AiSignalStatus.module.css';

const LEAVE_MS = 500; // the outgoing text is removed after its slide (0.45 s)

export default function AiSignalStatus({ status, steps = ['Thinking…'], startedAt, stepMs = 2500, markSize = 22 }) {
  const [shownAt] = useState(() => Date.now());
  const start = startedAt ? new Date(startedAt).getTime() : shownAt;
  const [now, setNow] = useState(() => Date.now());
  const text = status ?? stepAt(steps, now - start, stepMs);

  // The lines of text: the current one, plus the one sliding out.
  const [lines, setLines] = useState(() => [{ key: 0, text, state: 'shown' }]);
  const nextKey = useRef(1);

  // The clock (also moves the steps on).
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);

  // A new step: it enters from below, the old one leaves through the top.
  // (A step that changes again mid-slide simply drops the unfinished line.)
  useEffect(() => {
    setLines((old) => {
      const current = old.find((line) => line.state !== 'leave');
      if (current?.text === text) return old;
      const key = nextKey.current++;
      return [
        ...old.filter((line) => line.state === 'shown').map((line) => ({ ...line, state: 'leave' })),
        { key, text, state: 'enter' },
      ];
    });
    let frame = requestAnimationFrame(() => {
      // One frame in the "enter" place, then it slides to its place.
      frame = requestAnimationFrame(() =>
        setLines((old) => old.map((line) => (line.state === 'enter' ? { ...line, state: 'shown' } : line))),
      );
    });
    const timer = setTimeout(() => setLines((old) => old.filter((line) => line.state !== 'leave')), LEAVE_MS);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, [text]);

  return (
    <div className={classes.signal} role="status" aria-live="polite">
      <AssistantMark size={markSize} active />
      <div className={classes.status}>
        {lines.map((line) => (
          <span key={line.key} className={classes[line.state]} aria-hidden={line.state === 'leave' || undefined}>
            {line.text}
          </span>
        ))}
      </div>
      <span className={classes.time} aria-hidden="true">
        {formatElapsed(now - start)}
      </span>
    </div>
  );
}
