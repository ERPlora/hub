// hub#2320 — a WRITE on the core's REST surface that the hub never answered must reach the screen
// with the same honest verdict a command gets (hub#906), not with the transport's technical line.
//
// hub#2288 gave the core REST READS (`GET` on flows, events, WhatsApp templates and attachments,
// the certificate, the print queue) the localized «could not load» sentence, and left the writes
// as they arrived: `request to /api/hub/flows failed: TypeError: Failed to fetch` or
// `unexpected response from /api/…: HTTP 502 text/html`, in English, on the flow editor, the
// templates tab, the certificate screen and the print queue. A write may have COMMITTED before the
// answer was lost, exactly like a command, so the only honest sentence is the command verdict:
// «we can't tell whether it completed — check before trying again».
//
// What these tests pin, for every write door of the scoped client:
//
//   1. the code stays SERVER_UNAVAILABLE and `outcomeUnknown` is true — the same contract a module
//      already reads on a failed command;
//   2. the message is the localized command verdict (en source, es translation), never the
//      technical line, which survives on `cause`;
//   3. the shell's notifier is told once, as for a command — the default net for a screen that
//      renders nothing;
//   4. a domain refusal on a write passes untouched: the hub answered, the outcome is known.
//
// The fetch stubs fail exactly like the real ones (lesson of hub#770).
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

function scopedWith(fetchImpl: typeof fetch, notes: Notification[] = []) {
  return new ErploraClient(new HttpWsTransport({ baseUrl: 'http://h', fetchImpl }), {
    notifier: (n) => notes.push(n),
  }).forModule('whatsapp_inbox');
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

/** The error of a core REST write the hub never answered, told with the command verdict. */
function assertUnknownOutcome(e: unknown, locale: string): true {
  assert.ok(e instanceof ErploraError, 'the module must receive a typed ErploraError');
  assert.equal(e.code, SERVER_UNAVAILABLE, 'the hub#782 code modules key on is kept');
  assert.equal(
    (e as { outcomeUnknown?: boolean }).outcomeUnknown,
    true,
    'a write may have committed: it carries the unknown-outcome verdict of a command',
  );
  for (const leak of ['request to ', '/api/', 'HTTP ', 'Failed to fetch', 'JSON']) {
    assert.ok(!e.message.includes(leak), `technical transport text reached the screen: ${e.message}`);
  }
  assert.equal(e.message, commandVerdictMessage(locale), 'not the command verdict in the active locale');
  const cause = (e as Error).cause;
  assert.ok(cause instanceof ErploraError, 'the transport error survives as cause, for logs');
  assert.equal(cause.code, SERVER_UNAVAILABLE);
  assert.ok(cause.message.includes('/api/'), `cause lost the technical line: ${cause.message}`);
  return true;
}

/** One write per door — every surface the issue names, and every write method (POST/PUT/DELETE). */
const WRITES: ReadonlyArray<[string, (c: ReturnType<typeof scopedWith>) => Promise<unknown>]> = [
  ['flows.create (POST)', (c) => c.flows.create({ name: 'Reorder', definition: {} })],
  ['flows.update (PUT)', (c) => c.flows.update('f1', { name: 'Reorder', definition: {}, enabled: true })],
  ['flows.remove (DELETE)', (c) => c.flows.remove('f1')],
  ['flows.activateTemplate (POST)', (c) => c.flows.activateTemplate('appointment_reminder')],
  ['events.retry (POST)', (c) => c.events.retry('e1')],
  ['whatsappTemplates.register (POST)', (c) => c.whatsappTemplates.register({ name: 'reminder', language: 'es' })],
  ['whatsappTemplates.remove (DELETE)', (c) => c.whatsappTemplates.remove('reminder')],
  ['certificate.put (PUT)', (c) => c.certificate.put({ pkcs12Base64: 'AAAA', password: 'x' })],
  ['certificate.remove (DELETE)', (c) => c.certificate.remove()],
  ['printQueue.retry (POST)', (c) => c.printQueue.retry('j1')],
  ['printQueue.discard (POST)', (c) => c.printQueue.discard('j1', 'paper jam')],
];

for (const [name, write] of WRITES) {
  test(`hub#2320: ${name} over a dead network gets the command verdict, not the technical line`, async () => {
    const notes: Notification[] = [];
    await assert.rejects(() => write(scopedWith(deadFetch, notes)), (e) => assertUnknownOutcome(e, 'es'));
    assert.equal(notes.length, 1, 'the shell net is told on every write door, as for a command');
  });
}

test('hub#2320: a core REST write behind the proxy 502 page gets the command verdict', async () => {
  await assert.rejects(
    () => scopedWith(proxy502Fetch).whatsappTemplates.register({ name: 'reminder', language: 'es' }),
    (e) => assertUnknownOutcome(e, 'es'),
  );
});

test('hub#2320: the verdict follows the active locale (en source)', async () => {
  await withLocale('en-GB', async () => {
    await assert.rejects(() => scopedWith(deadFetch).flows.remove('f1'), (e) => assertUnknownOutcome(e, 'en'));
  });
});

test('hub#2320: the shell notifier is told once, as for a failed command', async () => {
  const notes: Notification[] = [];
  await assert.rejects(() => scopedWith(deadFetch, notes).certificate.remove());
  assert.equal(notes.length, 1, 'exactly one toast per failed write');
  assert.equal(notes[0]!.type, 'error');
  assert.equal(notes[0]!.message, commandVerdictMessage('es'));
});

test('hub#2320: a core REST read is still a read — no verdict, no toast', async () => {
  const notes: Notification[] = [];
  await assert.rejects(
    () => scopedWith(deadFetch, notes).flows.list(),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal((e as { outcomeUnknown?: boolean }).outcomeUnknown, undefined, 'a read commits nothing');
      assert.notEqual(e.message, commandVerdictMessage('es'));
      return true;
    },
  );
  assert.equal(notes.length, 0, 'load errors are presented by the screen, not the command net');
});

test('hub#2320: a domain refusal on a core REST write keeps its own code and sentence', async () => {
  const notes: Notification[] = [];
  const refusalFetch = (async () => ({
    ok: false,
    status: 403,
    headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => ({ ok: false, error: { code: 'capability_denied', message: 'Permiso no concedido' } }),
  })) as unknown as typeof fetch;
  await assert.rejects(
    () => scopedWith(refusalFetch, notes).whatsappTemplates.register({ name: 'reminder', language: 'es' }),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'capability_denied');
      assert.equal((e as { outcomeUnknown?: boolean }).outcomeUnknown, undefined);
      return true;
    },
  );
  assert.equal(notes.length, 0, 'a refusal is the module business, not the net');
});
