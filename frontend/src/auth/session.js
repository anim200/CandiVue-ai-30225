// Who is signed in, in THIS browser tab.
// sessionStorage (not localStorage) keeps every tab separate, so an
// interviewer tab and a candidate tab can run side by side in the two-tab
// demo. Closing the tab signs out.
// Stored: { token, user: { role, name, email, session_id } }

const KEY = 'candivue-session';

export function saveSession(session) {
  sessionStorage.setItem(KEY, JSON.stringify(session));
}

export function loadSession() {
  try {
    const saved = sessionStorage.getItem(KEY);
    return saved ? JSON.parse(saved) : null;
  } catch {
    return null; // storage blocked or damaged: treat as signed out
  }
}

export function clearSession() {
  sessionStorage.removeItem(KEY);
}
