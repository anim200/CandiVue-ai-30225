// The only place that talks to the backend. Every screen uses these helpers,
// so a failure always reaches the user as a plain-language message (N12, N25).
// The address is always /api/...: nginx (Docker) or Vite (npm run dev)
// forwards it to the backend.

import { clearSession, loadSession } from '../auth/session';

const TIMEOUT_MS = 15000;
const AI_TIMEOUT_MS = 120000; // an AI turn (e.g. writing a JD) can take a while
const UPLOAD_TIMEOUT_MS = 60000;

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

// Send one request to the backend (with the login token) and return the JSON answer, or throw an ApiError with a plain message.
// body: a plain object (sent as JSON) or FormData (file uploads).
// timeoutMs: AI requests may take longer than the default.
async function request(method, path, body, timeoutMs = TIMEOUT_MS) {
  const session = loadSession();
  const isForm = body instanceof FormData;
  const headers = { Accept: 'application/json' };
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (session) headers.Authorization = `Bearer ${session.token}`; // who is calling

  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined || isForm ? body : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
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
  return response.status === 204 ? null : response.json(); // 204 = done, no content
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

// Read data from the backend (GET).
export function apiGet(path) {
  return request('GET', path);
}

// Send data to the backend (POST).
export function apiPost(path, body) {
  return request('POST', path, body);
}

// Change something on the backend (PUT).
export function apiPut(path, body) {
  return request('PUT', path, body);
}

// Ask the AI to do something (POST). Allows up to 2 minutes, like nginx.
export function apiPostAi(path, body) {
  return request('POST', path, body, AI_TIMEOUT_MS);
}

// Upload files (POST as multipart form data).
export function apiUpload(path, formData) {
  return request('POST', path, formData, UPLOAD_TIMEOUT_MS);
}

// Delete something on the backend (DELETE).
export function apiDelete(path) {
  return request('DELETE', path);
}

// Ask the backend whether it and its database are working.
export function getHealth() {
  return apiGet('/health');
}
