// `withRetry`: one more try when a dev server refused the connection (another session saved a file
// and runserver restarted), never when the product answered wrong.
import { AssertionError } from 'node:assert';

import { describe, expect, it, vi } from 'vitest';

import { isConnectionRefused, withRetry } from './retry';

const refused = () => new Error('page.waitForURL: net::ERR_CONNECTION_REFUSED at http://localhost:8001/accounts/login/');

/** An `fn` that throws each of `errors` in turn, then returns `value`. */
function failing<T>(errors: unknown[], value: T) {
  const queue = [...errors];
  return vi.fn(async () => {
    if (queue.length) throw queue.shift();
    return value;
  });
}

const noSleep = () => vi.fn<(ms: number) => Promise<void>>(async () => {});

describe('withRetry', () => {
  it('returns the first result without waiting', async () => {
    const fn = failing([], 'in the hub');
    const sleep = noSleep();

    await expect(withRetry(fn, { sleep })).resolves.toBe('in the hub');
    expect(fn).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it('tries once more after a refused connection, about a second later', async () => {
    const fn = failing([refused()], 'in the hub');
    const sleep = noSleep();

    await expect(withRetry(fn, { sleep })).resolves.toBe('in the hub');
    expect(fn).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledExactlyOnceWith(1000);
  });

  it('gives up after the second refusal, with that error', async () => {
    const second = new Error('page.goto: net::ERR_CONNECTION_REFUSED at http://a.localhost:8000/demo/items');
    const fn = failing([refused(), second], 'never');
    const sleep = noSleep();

    await expect(withRetry(fn, { sleep })).rejects.toBe(second);
    expect(fn).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledTimes(1);
  });

  it('never retries an assertion or any other error', async () => {
    const expectError = Object.assign(new Error('expected net::ERR_ABORTED in the log'), {
      matcherResult: { pass: false, message: '' },
    });
    for (const error of [
      expectError,
      new AssertionError({ message: 'net::ERR_CONNECTION_REFUSED expected' }),
      new Error('page.waitForURL: Timeout 30000ms exceeded.'),
      new Error("login on http://a.localhost:8000: neither the SaaS nor the hub's shell showed up"),
      'net::ERR_CONNECTION_REFUSED',
    ]) {
      const fn = failing([error], 'never');
      const sleep = noSleep();

      await expect(withRetry(fn, { sleep })).rejects.toBe(error);
      expect(fn).toHaveBeenCalledTimes(1);
      expect(sleep).not.toHaveBeenCalled();
    }
  });

  it('tells about each retry and takes its own attempts and rule', async () => {
    const flaky = new Error('flaky');
    const fn = failing([flaky, flaky], 'third time');
    const sleep = noSleep();
    const onRetry = vi.fn();

    await expect(
      withRetry(fn, { attempts: 3, isRetryable: (error) => error === flaky, sleep, delayMs: 10, onRetry }),
    ).resolves.toBe('third time');
    expect(fn).toHaveBeenCalledTimes(3);
    expect(sleep.mock.calls).toEqual([[10], [10]]);
    expect(onRetry.mock.calls).toEqual([
      [flaky, 1],
      [flaky, 2],
    ]);
  });
});

describe('isConnectionRefused', () => {
  it.each([
    'page.waitForURL: net::ERR_CONNECTION_REFUSED at http://localhost:8001/accounts/login/',
    'page.goto: net::ERR_CONNECTION_RESET at http://a.localhost:8000/demo/items',
    'apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:8000',
    'ERR_CONNECTION_REFUSED',
  ])('is true for %s', (message) => {
    expect(isConnectionRefused(new Error(message))).toBe(true);
  });

  it('is false for a timeout, an assertion and anything that is no Error', () => {
    expect(isConnectionRefused(new Error('Timeout 30000ms exceeded.'))).toBe(false);
    expect(isConnectionRefused(new AssertionError({ message: 'ECONNREFUSED' }))).toBe(false);
    expect(isConnectionRefused('net::ERR_CONNECTION_REFUSED')).toBe(false);
    expect(isConnectionRefused(undefined)).toBe(false);
  });
});
