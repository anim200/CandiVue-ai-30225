// The only place that talks to the backend. Every screen uses these helpers,
// so a failure always reaches the user as a plain-language message (N12, N25).
// The address is always /api/...: nginx (Docker) or Vite (npm run dev)
// forwards it to the backend.

import { clearSession, loadSession } from '../auth/session';

const TIMEOUT_MS = 15000;

export const MESSAGES = {
  unreachable: 'Cannot reach the CandiVue server. Check that it is running and try again.',
  timeout: 'The server took too long to answer. Please try again.',
  failed: 'Something went wrong on the server. Please try again.',
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status; // HTTP status code, or 0 if the server was not reached
  }
}

async function request(method, path, body) {
  const session = loadSession();
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (session) headers.Authorization = `Bearer ${session.token}`; // who is calling

  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (error) {
    const message = error.name === 'TimeoutError' ? MESSAGES.timeout : MESSAGES.unreachable;
    throw new ApiError(message, 0);
  }

  // 401 with a token = the token expired or is no longer valid: sign out.
  // An interviewer goes back to the login page with a short explanation.
  if (response.status === 401 && session) {
    clearSession();
    if (session.user.role === 'interviewer') window.location.assign('/login?expired=1');
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(detail ?? MESSAGES.failed, response.status);
  }
  return response.json();
}

// The backend puts its safe, plain message in "detail" (FastAPI style).
// Anything else (no JSON, a list of validation errors) gets the general message.
async function readDetail(response) {
  try {
    const body = await response.json();
    return typeof body.detail === 'string' ? body.detail : null;
  } catch {
    return null;
  }
}

export function apiGet(path) {
  return request('GET', path);
}

export function apiPost(path, body) {
  return request('POST', path, body);
}

export function getHealth() {
  return apiGet('/health');
}
