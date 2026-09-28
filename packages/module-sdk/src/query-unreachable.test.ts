// hub#2288 — a READ the hub never answered must reach the screen as a sentence a person can act on.
//
// hub#782 collapsed every transport failure (dead network, the proxy's `502 text/html` page, a
// body that is not JSON) into `ErploraError(SERVER_UNAVAILABLE)`, and hub#906 put the honest,
// localized verdict on the COMMAND path. The query path was left with the transport's own line —
// `request to /api/query failed: TypeError: Failed to fetch` — and every module paints
// `e.message` (the list controller included), so a Spanish hub showed English plumbing while a
// screen was loading.
//
// What these tests pin, for every read door of `ErploraClient` (`query`, `queryOptional`,
// `queryPage`, `queryAll`, `queryAllOptional`) and for the list controller that sits on top:
//
//   1. the code stays SERVER_UNAVAILABLE (modules already key on it since hub#782);
//   2. the message is the localized «could not load — check the connection and try again» sentence
//      (en source, es translation), never the technical line;
//   3. the technical line survives on `cause`, for logs;
//   4. nothing else changes: no unknown-outcome verdict (a read commits nothing), no toast, a domain
//      refusal keeps its own sentence, and an absent optional module is still `undefined`.
//
// The fetch stubs fail exactly like the real ones (lesson of hub#770): WebKit/Chromium reject
// before any body exists, and the proxy answers `502 text/html`.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  ListController,
  SERVER_UNAVAILABLE,
  type Notification,
} from './index.ts';

/** Chromium's network-level failure: `fetch` rejects before any response exists. */
const deadFetch = (async () => {
  throw new TypeError('Failed to fetch');
}) as unknown as typeof fetch;

/** The proxy's answer while the hub container is down: a 502 HTML page. */
const proxy502Fetch = (async () => ({
  ok: false,
  status: 502,
  headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'text/html' : null) },
  json: async () => JSON.parse('<!DOCTYPE html><html>bad gateway</html>'),
})) as unknown as typeof fetch;

/** A proxy page mislabelled as JSON: the parser blows up on it. */
const brokenJsonFetch = (async () => ({
  ok: false,
  status: 502,
  headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'application/json' : null) },
  json: async () => JSON.parse('<!DOCTYPE html>'),
})) as unknown as typeof fetch;

const ES_SENTENCE = 'Comprueba la conexión e inténtalo de nuevo';
const EN_SENTENCE = 'Check the connection and try again';

function clientWith(fetchImpl: typeof fetch, notes: Notification[] = []): ErploraClient {
  return new ErploraClient(new HttpWsTransport({ baseUrl: 'http://h', fetchImpl }), {
    notifier: (n) => notes.push(n),
  });
}

/** The error a module receives from a read the hub never answered, in `sentence`'s language. */
function assertUnreachableRead(e: unknown, sentence: string): true {
  assert.ok(e instanceof ErploraError, 'the module must receive a typed ErploraError');
  assert.equal(e.code, SERVER_UNAVAILABLE, 'the hub#782 code modules key on is kept');
  for (const leak of ['request to ', '/api/', 'HTTP ', 'Failed to fetch', 'JSON']) {
    assert.ok(!e.message.includes(leak), `technical transport text reached the screen: ${e.message}`);
  }
  assert.ok(e.message.includes(sentence), `not the localized read sentence: ${e.message}`);
  assert.equal(
    (e as { outcomeUnknown?: boolean }).outcomeUnknown,
    undefined,
    'a read commits nothing: it never carries the command verdict',
  );
  const cause = (e as Error).cause;
  assert.ok(cause instanceof ErploraError, 'the transport error survives as cause, for logs');
  assert.equal(cause.code, SERVER_UNAVAILABLE);
  assert.ok(cause.message.includes('/api/query'), `cause lost the technical line: ${cause.message}`);
  return true;
}

async function withLocale(locale: string, body: () => Promise<void>): Promise<void> {
  const g = globalThis as { localStorage?: unknown };
  const prev = g.localStorage;
  g.localStorage = { getItem: (k: string) => (k === 'erplora.locale' ? locale : null) };
  try {
    await body();
  } finally {
    if (prev === undefined) delete g.localStorage;
    else g.localStorage = prev;
  }
}

test('hub#2288: query() over a dead network rejects with the localized read sentence', async () => {
  const notes: Notification[] = [];
  await assert.rejects(
    () => clientWith(deadFetch, notes).query('customers.list'),
    (e) => assertUnreachableRead(e, ES_SENTENCE),
  );
  assert.equal(notes.length, 0, 'a failed read is shown by the screen, never toasted by the net');
});

test('hub#2288: queryPage() against the proxy 502 page rejects with the read sentence', async () => {
  await assert.rejects(
    () => clientWith(proxy502Fetch).queryPage('customers.list', { limit: 50 }),
    (e) => assertUnreachableRead(e, ES_SENTENCE),
  );
});

test('hub#2288: queryAll() on a body that is not JSON rejects with the read sentence', async () => {
  await assert.rejects(
    () => clientWith(brokenJsonFetch).queryAll('inventory.products.list'),
    (e) => assertUnreachableRead(e, ES_SENTENCE),
  );
});

test('hub#2288: the optional reads do not take an unreachable hub for an absent module', async () => {
  const client = clientWith(deadFetch);
  await assert.rejects(
    () => client.queryOptional('verifactu.status'),
    (e) => assertUnreachableRead(e, ES_SENTENCE),
  );
  await assert.rejects(
    () => client.queryAllOptional('taxes.rules.list'),
    (e) => assertUnreachableRead(e, ES_SENTENCE),
  );
});

test('hub#2288: the sentence follows the active locale (en source)', async () => {
  await withLocale('en', async () => {
    await assert.rejects(
      () => clientWith(deadFetch).query('customers.list'),
      (e) => assertUnreachableRead(e, EN_SENTENCE),
    );
    // The list path (`queryPage`, under the list controller) resolves the locale too.
    const ctrl = new ListController(clientWith(proxy502Fetch), 'customers.list');
    await ctrl.load();
    assert.ok(ctrl.error.includes(EN_SENTENCE), `the list is not in the active locale: ${ctrl.error}`);
  });
});

test('hub#2288: the list controller shows the read sentence, not the transport line', async () => {
  const ctrl = new ListController(clientWith(proxy502Fetch), 'customers.list');
  await ctrl.load();
  assert.equal(ctrl.loading, false);
  assert.deepEqual(ctrl.rows, []);
  assert.ok(!ctrl.error.includes('request to '), `technical line on the list: ${ctrl.error}`);
  assert.ok(!ctrl.error.includes('/api/'), `technical line on the list: ${ctrl.error}`);
  assert.ok(ctrl.error.includes(ES_SENTENCE), `not the read sentence: ${ctrl.error}`);
});

test('hub#2288: a domain refusal on a read keeps its own code and sentence', async () => {
  const refusalFetch = (async () => ({
    ok: false,
    status: 409,
    headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => ({ ok: false, error: { code: 'customers.not_found', message: 'Cliente no encontrado' } }),
  })) as unknown as typeof fetch;
  await assert.rejects(
    () => clientWith(refusalFetch).query('customers.get', { id: 'x' }),
    (e: unknown) =>
      e instanceof ErploraError && e.code === 'customers.not_found' && e.message === 'Cliente no encontrado',
  );
});

test('hub#2288: an absent optional module is still `undefined`, not the read sentence', async () => {
  const absentFetch = (async () => ({
    ok: false,
    status: 404,
    headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => ({ ok: false, error: { code: 'module_not_installed', module: 'verifactu', message: '' } }),
  })) as unknown as typeof fetch;
  assert.equal(await clientWith(absentFetch).queryOptional('verifactu.status'), undefined);
  assert.equal(await clientWith(absentFetch).queryAllOptional('verifactu.records.list'), undefined);
});

// The core's own REST surface (flows, event catalogue, WhatsApp templates and attachments, the
// business certificate, the print queue) is read by module screens too — the flow gallery, the
// templates tab — and went through the same transport exits. A GET there is a read like any query.

/** The error of a core REST read the hub never answered, with the technical line on `cause`. */
function assertUnreachableCoreRead(e: unknown, path: string): true {
  assert.ok(e instanceof ErploraError, 'the module must receive a typed ErploraError');
  assert.equal(e.code, SERVER_UNAVAILABLE);
  assert.ok(!e.message.includes('request to ') && !e.message.includes('/api/'), `technical text: ${e.message}`);
  assert.ok(e.message.includes(ES_SENTENCE), `not the read sentence: ${e.message}`);
  const cause = (e as Error).cause;
  assert.ok(cause instanceof ErploraError && cause.message.includes(path), 'cause keeps the technical line');
  return true;
}

test('hub#2288: a core REST read (templates, flows, events, certificate) gets the read sentence', async () => {
  const scoped = (f: typeof fetch) => clientWith(f).forModule('whatsapp_inbox');
  await assert.rejects(() => scoped(deadFetch).whatsappTemplates.list(), (e) => assertUnreachableCoreRead(e, '/api/'));
  await assert.rejects(() => scoped(proxy502Fetch).flows.list(), (e) => assertUnreachableCoreRead(e, '/api/'));
  await assert.rejects(() => scoped(brokenJsonFetch).events.list(), (e) => assertUnreachableCoreRead(e, '/api/'));
  await assert.rejects(() => scoped(deadFetch).certificate.get(), (e) => assertUnreachableCoreRead(e, '/api/'));
});

test('hub#2288: an attachment the hub never sent gets the read sentence', async () => {
  await assert.rejects(
    () => clientWith(deadFetch).forModule('whatsapp_inbox').whatsappMedia.get('1234567890'),
    (e) => assertUnreachableCoreRead(e, '/api/'),
  );
});

test('hub#2288: a core REST WRITE is never told «the data could not be loaded»', async () => {
  await assert.rejects(
    () => clientWith(deadFetch).forModule('whatsapp_inbox').flows.remove('f1'),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, SERVER_UNAVAILABLE);
      assert.ok(!e.message.includes(ES_SENTENCE), `a write was described as a failed load: ${e.message}`);
      return true;
    },
  );
});
