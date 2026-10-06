// Tests for the API helper. fetch, the tab storage and the page address are
// replaced by fakes, so no backend or browser is needed.

import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import { loadSession, saveSession } from '../auth/session';
import { apiGet, apiPost, apiPut, MESSAGES } from './client';

// Replace the browser's fetch with a fake that answers with the given handler.
function fakeFetch(handler) {
  vi.stubGlobal('fetch', vi.fn(handler));
}

// A minimal stand-in for the browser's sessionStorage and window.location.
beforeEach(() => {
  const store = new Map();
  vi.stubGlobal('sessionStorage', {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => store.set(key, value),
    removeItem: (key) => store.delete(key),
  });
  vi.stubGlobal('window', { location: { assign: vi.fn() } });
});

// Build a fake JSON answer with the given status code.
function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test('returns the data when the backend answers', async () => {
  fakeFetch(async () => jsonResponse({ status: 'ok', database: 'ok' }, 200));

  await expect(apiGet('/health')).resolves.toEqual({ status: 'ok', database: 'ok' });
  expect(fetch).toHaveBeenCalledWith('/api/health', expect.any(Object));
});

test('gives a plain message when the server cannot be reached', async () => {
  fakeFetch(async () => {
    throw new TypeError('Failed to fetch');
  });

  await expect(apiGet('/health')).rejects.toMatchObject({
    status: 0,
    message: MESSAGES.unreachable,
  });
});

test('gives a plain message when the server is too slow', async () => {
  fakeFetch(async () => {
    throw new DOMException('signal timed out', 'TimeoutError');
  });

  await expect(apiGet('/health')).rejects.toMatchObject({ message: MESSAGES.timeout });
});

test("shows the backend's own message for an error answer", async () => {
  fakeFetch(async () => jsonResponse({ detail: 'The AI service is unavailable.' }, 503));

  await expect(apiGet('/health')).rejects.toMatchObject({
    status: 503,
    message: 'The AI service is unavailable.',
  });
});

test('hides technical details the backend did not mean to show', async () => {
  fakeFetch(async () => new Response('Traceback (most recent call last): ...', { status: 500 }));

  const error = await apiGet('/health').catch((e) => e);

  expect(error.message).toBe(MESSAGES.failed);
  expect(error.message).not.toContain('Traceback');
});

test('sends the token of the signed-in user', async () => {
  saveSession({ token: 'abc123', user: { role: 'interviewer', name: 'Interviewer A' } });
  fakeFetch(async () => jsonResponse({ ok: true }, 200));

  await apiGet('/auth/me');

  const [, options] = fetch.mock.calls[0];
  expect(options.headers.Authorization).toBe('Bearer abc123');
});

test('sends JSON for a POST', async () => {
  fakeFetch(async () => jsonResponse({ ok: true }, 200));

  await apiPost('/auth/login', { email: 'a@example.com', password: 'x' });

  const [, options] = fetch.mock.calls[0];
  expect(options.method).toBe('POST');
  expect(options.headers['Content-Type']).toBe('application/json');
  expect(JSON.parse(options.body)).toEqual({ email: 'a@example.com', password: 'x' });
});

test('sends JSON for a PUT (e.g. choosing the AI model)', async () => {
  fakeFetch(async () => jsonResponse({ models: [] }, 200));

  await apiPut('/ai/model', { name: 'gemini-3.5-flash-lite' });

  const [path, options] = fetch.mock.calls[0];
  expect(path).toBe('/api/ai/model');
  expect(options.method).toBe('PUT');
  expect(JSON.parse(options.body)).toEqual({ name: 'gemini-3.5-flash-lite' });
});

test('an expired session signs the interviewer out and opens the login page', async () => {
  saveSession({ token: 'old', user: { role: 'interviewer', name: 'Interviewer A' } });
  fakeFetch(async () =>
    jsonResponse({ detail: 'Your session has expired. Please sign in again.' }, 401),
  );

  await expect(apiGet('/auth/me')).rejects.toMatchObject({ status: 401 });

  expect(loadSession()).toBeNull();
  expect(window.location.assign).toHaveBeenCalledWith('/login?expired=1');
});

test('a wrong password does not redirect anywhere', async () => {
  fakeFetch(async () => jsonResponse({ detail: 'Email or password is incorrect.' }, 401));

  await expect(apiPost('/auth/login', {})).rejects.toMatchObject({
    message: 'Email or password is incorrect.',
  });
  expect(window.location.assign).not.toHaveBeenCalled();
});
