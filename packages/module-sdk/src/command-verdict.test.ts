// hub#906 — a hub that dies mid-command must leave the user with an HONEST verdict.
//
// The real incident (saas#1460): the hub container is OOM-killed (exit 137) right after
// `complete_sale` commits. The runtime answered 200 to itself, the client never received the
// response, and the cashier saw WebKit's raw «The string did not match the expected pattern.» —
// so she charged again: double charge, duplicated fiscal document.
//
// hub#782 already collapses every transport failure into `ErploraError(SERVER_UNAVAILABLE)`, but
// on the COMMAND path that is not enough: a query that failed did nothing, while a command that
// failed may have COMMITTED. The client cannot know which — and «we can't know» is exactly the
// verdict it must present. These tests pin the command path of `ErploraClient`:
//
//   1. the error the module receives says the outcome is UNKNOWN (`outcomeUnknown: true`) and its
//      message is the honest, localized sentence — never `request to /api/command failed: …`;
//   2. the shell's notifier (already wired to the global toast in `apps/web/src/lib/runtime.ts`)
//      is told once, as the default net for modules that render nothing;
//   3. a domain refusal and a failed QUERY are untouched: nothing committed there, so no unknown
//      verdict and no toast.
//
// Lesson of hub#770 honored: the fetch stub fails exactly like the real one fails — WebKit rejects
// with `TypeError: Load failed` before any body exists, and the proxy answers `502 text/html`.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  SERVER_UNAVAILABLE,
  type Notification,
} from './index.ts';

/** WebKit's network-level failure: `fetch` rejects before any response exists. */
const webkitDeadFetch = (async () => {
  throw new TypeError('Load failed');
}) as unknown as typeof fetch;

/** The proxy's answer while the hub container is down (OOM exit 137): a 502 HTML page. */
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

test('hub#906: a command whose transport dies rejects with the honest unknown-outcome verdict', async () => {
  const notes: Notification[] = [];
  const client = clientWith(webkitDeadFetch, notes);
  await assert.rejects(
    () => client.command('sales.complete_sale', { payments: [{ method: 'cash', amount: 3090 }] }),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError, 'the module must receive a typed ErploraError');
      // hub#782's code survives: modules that already key on it keep working.
      assert.equal(e.code, SERVER_UNAVAILABLE);
      // The verdict is a FIELD, not a message to parse — and it survives bundle duplication.
      assert.equal(
        (e as { outcomeUnknown?: boolean }).outcomeUnknown,
        true,
        'a failed command has an UNKNOWN outcome: it may have committed before the hub died',
      );
      // The message is the honest sentence, not the technical log line.
      assert.ok(
        !e.message.includes('request to '),
        `technical transport message leaked to the user: ${e.message}`,
      );
      assert.ok(
        e.message.includes('No sabemos si la operación se completó'),
        `not the honest es sentence: ${e.message}`,
      );
      return true;
    },
  );
});

test('hub#906: the shell notifier (global toast net) is told once, with the honest message', async () => {
  const notes: Notification[] = [];
  const client = clientWith(proxy502Fetch, notes);
  await assert.rejects(() => client.command('sales.complete_sale'));
  assert.equal(notes.length, 1, 'exactly one toast per failed command');
  assert.equal(notes[0].type, 'error');
  assert.ok(notes[0].message.includes('No sabemos si la operación se completó'));
  // hub#2342: the net is the verdict of EVERY command, so it no longer carries the charge tail;
  // the «check Sales before charging again» guidance is the POS's own panel (sales#91).
  assert.ok(
    notes[0].message.includes('Comprueba el resultado antes de reintentar'),
    'the net must tell the user to check before retrying',
  );
});

test('hub#906: the honest sentence follows the active locale (en source)', async () => {
  const g = globalThis as { localStorage?: unknown };
  const prev = g.localStorage;
  g.localStorage = { getItem: (k: string) => (k === 'erplora.locale' ? 'en' : null) };
  try {
    const notes: Notification[] = [];
    const client = clientWith(webkitDeadFetch, notes);
    await assert.rejects(
      () => client.command('sales.complete_sale'),
      (e: unknown) =>
        e instanceof ErploraError &&
        e.message.includes("We can't tell whether the operation completed"),
    );
  } finally {
    if (prev === undefined) delete g.localStorage;
    else g.localStorage = prev;
  }
});

test('hub#906: the technical detail is kept on `cause` for logs, not shown', async () => {
  const notes: Notification[] = [];
  const client = clientWith(webkitDeadFetch, notes);
  await assert.rejects(
    () => client.command('sales.complete_sale'),
    (e: unknown) => {
      const cause = (e as Error).cause;
      assert.ok(cause instanceof ErploraError, 'the original transport error survives as cause');
      assert.equal(cause.code, SERVER_UNAVAILABLE);
      assert.ok(cause.message.includes('request to '), 'cause keeps the technical line');
      return true;
    },
  );
});

test('hub#906: a domain refusal is untouched — its outcome is KNOWN (the hub said no)', async () => {
  const refusalFetch = (async () => ({
    ok: false,
    status: 403,
    headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => ({ ok: false, error: { code: 'permission_denied', message: 'no' } }),
  })) as unknown as typeof fetch;
  const notes: Notification[] = [];
  const client = clientWith(refusalFetch, notes);
  await assert.rejects(
    () => client.command('sales.complete_sale'),
    (e: unknown) =>
      e instanceof ErploraError &&
      e.code === 'permission_denied' &&
      (e as { outcomeUnknown?: boolean }).outcomeUnknown === undefined,
  );
  assert.equal(notes.length, 0, 'a refusal is the module business, not the net');
});

test('hub#906: a failed QUERY stays a plain transport error — nothing committed, no toast', async () => {
  const notes: Notification[] = [];
  const client = clientWith(webkitDeadFetch, notes);
  await assert.rejects(
    () => client.query('sales.sales.list'),
    (e: unknown) =>
      e instanceof ErploraError &&
      e.code === SERVER_UNAVAILABLE &&
      (e as { outcomeUnknown?: boolean }).outcomeUnknown === undefined,
  );
  assert.equal(notes.length, 0, 'load errors are presented by list states, not the command net');
});
