// hub#2375 — a screen that resolves an unknown outcome ITSELF must not be contradicted by the net.
//
// hub#906 gave every command the hub never answered an honest verdict, and told the shell's
// notifier once as the default net (a red toast: «we can't tell whether it completed — check
// before trying again»). Some screens do better than the net: the refund of `sales` (sales#456)
// probes by its idempotency key as soon as the hub is back and says, on the screen, «the refund
// was not recorded — you can refund again, it won't be duplicated». With the toast still up
// saying the opposite, the person at the counter reads two contradicting sentences at once.
//
// So a call may declare `{ resolvesOutcome: true }`: the caller still gets the SAME
// `UnknownOutcomeError` (it is what tells it to probe), but the shell's toast is skipped for THAT
// call. A module that says nothing keeps the net — the default never changes.
//
// Lesson of hub#770 honored: the fetch stubs fail exactly like the real ones do.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  SERVER_UNAVAILABLE,
  commandVerdictMessage,
  type Notification,
} from './index.ts';

/** WebKit's network-level failure: `fetch` rejects before any response exists. */
const webkitDeadFetch = (async () => {
  throw new TypeError('Load failed');
}) as unknown as typeof fetch;

/** The proxy's answer while the hub container is down: a 502 HTML page. */
const proxy502Fetch = (async () => ({
  ok: false,
  status: 502,
  headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'text/html' : null) },
  json: async () => JSON.parse('<!DOCTYPE html><html>bad gateway</html>'),
})) as unknown as typeof fetch;

function clientWith(fetchImpl: typeof fetch, notes: Notification[]): ErploraClient {
  return new ErploraClient(new HttpWsTransport({ baseUrl: 'http://h', fetchImpl }), {
    notifier: (n) => notes.push(n),
  });
}

/** The caller still receives the unknown-outcome verdict: it is what tells the screen to probe. */
function isUnknownOutcome(e: unknown): true {
  assert.ok(e instanceof ErploraError, 'the module must receive a typed ErploraError');
  assert.equal(e.code, SERVER_UNAVAILABLE, 'the hub#782 code modules key on is kept');
  assert.equal(
    (e as { outcomeUnknown?: boolean }).outcomeUnknown,
    true,
    'silencing the toast must not hide the verdict from the caller',
  );
  assert.equal(e.message, commandVerdictMessage('es'), 'the honest sentence, for the screen to reuse');
  return true;
}

for (const [how, fetchImpl] of [
  ['a dead network', webkitDeadFetch],
  ['the proxy 502 page', proxy502Fetch],
] as const) {
  test(`hub#2375: resolvesOutcome skips the shell toast on ${how}, and still rejects with the verdict`, async () => {
    const notes: Notification[] = [];
    await assert.rejects(
      () => clientWith(fetchImpl, notes).command('sales.refund', { sale_id: 's1' }, { resolvesOutcome: true }),
      isUnknownOutcome,
    );
    assert.equal(notes.length, 0, 'the screen resolves the doubt itself: no contradicting red toast');
  });
}

test('hub#2375: without the option the net stays — one toast, as since hub#906', async () => {
  const notes: Notification[] = [];
  await assert.rejects(() => clientWith(webkitDeadFetch, notes).command('sales.refund', {}), isUnknownOutcome);
  assert.equal(notes.length, 1, 'a module that says nothing keeps the default net');
});

test('hub#2375: resolvesOutcome false (or an empty options object) keeps the net', async () => {
  for (const opts of [{ resolvesOutcome: false }, {}]) {
    const notes: Notification[] = [];
    await assert.rejects(() => clientWith(webkitDeadFetch, notes).command('sales.refund', {}, opts), isUnknownOutcome);
    assert.equal(notes.length, 1, `only an explicit true silences the net (${JSON.stringify(opts)})`);
  }
});

test('hub#2375: the option is per CALL — the next call on the same client without it toasts', async () => {
  const notes: Notification[] = [];
  const client = clientWith(webkitDeadFetch, notes);
  await assert.rejects(() => client.command('sales.refund', {}, { resolvesOutcome: true }), isUnknownOutcome);
  await assert.rejects(() => client.command('sales.complete_sale', {}), isUnknownOutcome);
  assert.equal(notes.length, 1, 'the silenced call leaves no sticky state behind');
});

test('hub#2375: the option never travels to the hub — the payload on the wire is the caller payload', async () => {
  const bodies: unknown[] = [];
  const recordingFetch = (async (_url: string, init?: { body?: string }) => {
    bodies.push(JSON.parse(init?.body ?? 'null'));
    return {
      ok: true,
      status: 200,
      headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'application/json' : null) },
      json: async () => ({ ok: true, data: { id: 'r1' } }),
    };
  }) as unknown as typeof fetch;
  const result = await clientWith(recordingFetch, []).command(
    'sales.refund',
    { sale_id: 's1', idempotency_key: 'k1' },
    { resolvesOutcome: true },
  );
  assert.deepEqual(result, { id: 'r1' }, 'a command that answered returns its data as always');
  assert.deepEqual(bodies, [{ name: 'sales.refund', payload: { sale_id: 's1', idempotency_key: 'k1' } }]);
});

test('hub#2375: a domain refusal with the option is untouched — its outcome is known', async () => {
  const refusalFetch = (async () => ({
    ok: false,
    status: 403,
    headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => ({ ok: false, error: { code: 'permission_denied', message: 'no' } }),
  })) as unknown as typeof fetch;
  const notes: Notification[] = [];
  await assert.rejects(
    () => clientWith(refusalFetch, notes).command('sales.refund', {}, { resolvesOutcome: true }),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'permission_denied');
      assert.equal((e as { outcomeUnknown?: boolean }).outcomeUnknown, undefined);
      return true;
    },
  );
  assert.equal(notes.length, 0);
});

test('hub#2375: commandOptional carries the option through to the verdict', async () => {
  const silenced: Notification[] = [];
  await assert.rejects(
    () => clientWith(webkitDeadFetch, silenced).commandOptional('inventory.products.create', {}, { resolvesOutcome: true }),
    isUnknownOutcome,
  );
  assert.equal(silenced.length, 0, 'commandOptional with the option must not toast either');

  const net: Notification[] = [];
  await assert.rejects(
    () => clientWith(webkitDeadFetch, net).commandOptional('inventory.products.create', {}),
    isUnknownOutcome,
  );
  assert.equal(net.length, 1, 'commandOptional without the option keeps the net');
});

test('hub#2375: the door a module actually holds — forModule(<id>) — honors the option too', async () => {
  const notes: Notification[] = [];
  const scoped = clientWith(webkitDeadFetch, notes).forModule('sales');
  await assert.rejects(() => scoped.command('sales.refund', {}, { resolvesOutcome: true }), isUnknownOutcome);
  assert.equal(notes.length, 0, 'the module-scoped client must not toast when the screen resolves the doubt');
  await assert.rejects(() => scoped.command('sales.refund', {}), isUnknownOutcome);
  assert.equal(notes.length, 1, 'and keeps the net when it does not');
});
