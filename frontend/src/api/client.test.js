// Tests for the API helper. fetch is replaced by a fake, so no backend is needed.

import { afterEach, expect, test, vi } from 'vitest';

import { apiGet, MESSAGES } from './client';

function fakeFetch(handler) {
  vi.stubGlobal('fetch', vi.fn(handler));
}

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
