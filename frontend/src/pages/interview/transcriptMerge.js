// Merging transcript turns (from the backend's answers and the transcriber's
// pushes) by id. The same Map comes back when nothing changed, so React does
// not re-render the transcript for a repeated or older copy of a turn.

export function mergeTurns(old, incoming) {
  let next = old;
  for (const turn of incoming) {
    const before = old.get(turn.id);
    if (before && before.text === turn.text && before.end_ms === turn.end_ms && before.start_ms === turn.start_ms) {
      continue;
    }
    if (next === old) next = new Map(old);
    next.set(turn.id, turn);
  }
  return next;
}
