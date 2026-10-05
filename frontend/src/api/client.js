// The only place that talks to the backend. Every screen uses these helpers,
// so a failure always reaches the user as a plain-language message (N12, N25).
// The address is always /api/...: nginx (Docker) or Vite (npm run dev)
// forwards it to the backend.

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

export async function apiGet(path) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (error) {
    const message = error.name === 'TimeoutError' ? MESSAGES.timeout : MESSAGES.unreachable;
    throw new ApiError(message, 0);
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

export function getHealth() {
  return apiGet('/health');
}
