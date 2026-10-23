// Helpers of the AI "Signal" status (AiSignalStatus.jsx), kept apart so
// they can be tested.

// Elapsed time since the AI request started: "4s", then "1m 05s".
export function formatElapsed(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
}

// The step to show after `elapsed` ms when there are no real events: one
// step every `every` ms, then the last one until the answer arrives (never
// back to the first).
export function stepAt(steps, elapsed, every) {
  const index = Math.min(Math.floor(Math.max(0, elapsed) / every), steps.length - 1);
  return steps[index];
}

// Steps for the Hiring Assistant's chat actions (no real events: the
// answer comes in one piece). A plain reply only "thinks".
export const CHAT_STEPS = {
  message: ['Thinking…'],
  reject: ['Reading your feedback…', 'Writing a new version…'],
  post: ['Preparing the job post…', 'Posting to the job board…'],
  invite: ['Checking the times…', 'Booking the interviews…', 'Sending the invitations…'],
};

// "Screening CV 3 of 5…" from a screening run's progress.
export function screeningStatus(run) {
  if (!run.total) return 'Reading CVs…';
  return `Screening CV ${Math.min(run.processed + 1, run.total)} of ${run.total}…`;
}
