// @vitest-environment node
// flow: ninguno — FIX of the e2e harness (hub#795)
// With the machine loaded, a spec fell in its first lines, turning an app on or reading the list of apps: the hub of the
// stack runs `a` with Free's limits (one transaction at once) and answered 503 `base.hub_busy` («Too many requests. Try
// again in a moment.») while the page just opened still held that place. `api` (the one way the e2e helpers ask the
// hub's API: `turnOn`, `manualFlow`, `createProduct`, the specs' own `post`…) handed that 503 back, and the spec fell on
// it, or on a `TypeError` that did not say why. The server says that answer ran nothing (`HubBusy` is refused before
// any statement, `OperationError.retry_after`), so `api` sends the same request again after the server's `Retry-After`,
// a few times, as a person would; a hub that stays busy still fails, saying so. The plan's limit is not touched.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { BrowserContext } from '@playwright/test';
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi } from 'vitest';

import { api } from './hub-api';

const E2E_DIR = dirname(fileURLToPath(import.meta.url));
const HUB_DIR = join(E2E_DIR, '..', '..');
const read = (path: string): string => readFileSync(path, 'utf8');

/** The seconds the server's 503 `base.hub_busy` asks to wait (`Retry-After`, `base.tenancy.limits`). */
function serverRetryAfterSeconds(): number {
  const found = /^RETRY_AFTER_SECONDS = (\d+(?:\.\d+)?)$/m.exec(read(join(HUB_DIR, 'base', 'tenancy', 'limits.py')));
  if (!found) throw new Error('RETRY_AFTER_SECONDS is no longer in base/tenancy/limits.py');
  return Number(found[1]);
}

const PAUSE_MS = serverRetryAfterSeconds() * 1000;
/** The first try and five more: about 15 s at most (each try waits up to 2 s for a place, then the pause). */
const TRIES = 6;

const A = 'http://a.localhost:27950';

interface Answer {
  status: number;
  body: unknown;
}

const busy = (): Answer => ({
  status: 503,
  body: { error: { code: 'base.hub_busy', message: 'Too many requests. Try again in a moment.' } },
});

/** A context whose requests get `answers` in turn, the last one again and again, and that notes each request sent. */
function fakeContext(answers: Answer[]) {
  const queue = [...answers];
  const sent: { method: string; url: string; options: unknown }[] = [];
  const respond = (method: string) =>
    vi.fn(async (url: string, options: unknown) => {
      sent.push({ method, url, options });
      const answer = queue.length > 1 ? queue.shift()! : queue[0];
      const text = answer.body === null ? '' : JSON.stringify(answer.body);
      return { status: () => answer.status, text: async () => text, headers: () => ({}) };
    });
  const context = {
    cookies: vi.fn(async () => [
      { name: 'csrftoken', value: 'saas-token', domain: 'localhost' },
      { name: 'csrftoken', value: 'hub-token', domain: 'a.localhost' },
    ]),
    request: { get: respond('GET'), post: respond('POST') },
  } as unknown as BrowserContext;
  return { context, sent };
}

/** What `promise` failed with, or `null` when it did not fail. */
const failure = (promise: Promise<unknown>): Promise<unknown> => promise.then(
  () => null,
  (error: unknown) => error,
);

/** The note each new try leaves in the run's output. */
let warn: MockInstance<typeof console.warn>;

beforeEach(() => {
  vi.useFakeTimers();
  warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('api and a hub busy for a moment (503 base.hub_busy)', () => {
  it('the server still asks to wait a whole number of seconds', () => {
    expect(PAUSE_MS).toBeGreaterThan(0);
  });

  it('sends the same request again after the server’s Retry-After, and answers what came then', async () => {
    const { context, sent } = fakeContext([busy(), { status: 201, body: { id: 'p1' } }]);

    const answer = api<{ id: string }>(context, A, 'POST', '/inventory/products', { sku: 'E2E-1', price: 100 });
    await vi.advanceTimersByTimeAsync(PAUSE_MS - 1);
    expect(sent).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);

    await expect(answer).resolves.toEqual({ status: 201, data: { id: 'p1' } });
    expect(sent).toHaveLength(2);
    expect(sent[1]).toEqual(sent[0]);
    expect(warn).toHaveBeenCalledOnce();
    expect(String(warn.mock.calls[0][0])).toContain('POST /api/inventory/products');
    expect(String(warn.mock.calls[0][0])).toContain('base.hub_busy');
    expect(sent[0]).toEqual({
      method: 'POST',
      url: `${A}/api/inventory/products`,
      options: { headers: { 'X-CSRFToken': 'hub-token', Accept: 'application/json' }, data: { sku: 'E2E-1', price: 100 } },
    });
  });

  it('keeps trying while it stays busy, a read as a write (the list of apps turnOn waits on)', async () => {
    const apps = { apps: [{ id: 'payment', state: 'on' }] };
    const { context, sent } = fakeContext([busy(), busy(), busy(), { status: 200, body: apps }]);

    const answer = api(context, A, 'GET', '/apps');
    await vi.runAllTimersAsync();

    await expect(answer).resolves.toEqual({ status: 200, data: apps });
    expect(sent.map((request) => `${request.method} ${request.url}`)).toEqual(Array(4).fill(`GET ${A}/api/apps`));
  });

  it('fails when the hub stays busy, naming the route, the tries and the server’s answer', async () => {
    const { context, sent } = fakeContext([busy()]);

    const failed = failure(api(context, A, 'POST', '/apps/enable', { app: 'payment' }));
    await vi.runAllTimersAsync();
    const error = await failed;

    expect(error).toBeInstanceOf(Error);
    const message = (error as Error).message;
    expect(message).toContain('POST /api/apps/enable');
    expect(message).toContain(`${TRIES} tries`);
    expect(message).toContain('503');
    expect(message).toContain('"code":"base.hub_busy"');
    expect(sent).toHaveLength(TRIES);
  });

  it.each<[string, Answer]>([
    ['a business being moved', { status: 503, body: { error: { code: 'base.hub_maintenance', message: 'm' } } }],
    ['a database that cannot be reached', { status: 503, body: { error: { code: 'base.hub_unavailable', message: 'm' } } }],
    ['an empty 503', { status: 503, body: null }],
    ['a conflict', { status: 409, body: { error: { code: 'base.app_required', message: 'm' } } }],
    ['a refusal', { status: 400, body: { error: { code: 'base.validation', message: 'm' } } }],
    ['a server error', { status: 500, body: { error: { code: 'error', message: 'm' } } }],
    ['a success', { status: 200, body: { apps: [] } }],
  ])('never sends again after %s: that answer is the caller’s to check', async (_name, given) => {
    const { context, sent } = fakeContext([given, { status: 200, body: { again: true } }]);

    const answer = api(context, A, 'POST', '/apps/enable', { app: 'payment' });
    await vi.runAllTimersAsync();

    await expect(answer).resolves.toEqual({ status: given.status, data: given.body });
    expect(sent).toHaveLength(1);
    expect(warn).not.toHaveBeenCalled();
  });
});

describe('the shared helpers ask the hub’s API only through api', () => {
  it('helpers.ts (turnOn, turnOnMissing, turnOffTurnedOn…) sends no request of its own', () => {
    const source = read(join(E2E_DIR, 'helpers.ts'));
    const own = source.split('\n').filter((line) => /\.request\.(get|post|put|patch|delete|fetch)\(/.test(line));

    expect(own).toEqual([]);
  });
});
