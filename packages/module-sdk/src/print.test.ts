// hub#1108 — the DECLARED way a module reaches the print queue's two recovery gestures.
//
// hub#1107 gave the READ: `hub.print.coverage` and `hub.print.jobs` are core queries and travel
// through the dispatcher like any other, so nothing new is needed here for them. Writing is not a
// query, and the print queue is core REST (the same reason flows are, ADR-0283 §9), so a module
// had no way in at all — and the thing it *could* do instead is the antipattern hub#714 removed:
// read the session token out of `localStorage` and `fetch` the door itself.
//
// So the surface is explicit, typed, module-scoped — and DELIBERATELY NOT a proxy. These tests are
// what stops it from becoming one: the method list is pinned, every URL it can produce is pinned to
// one prefix, and a `jobId` that would climb out of that prefix is refused before a request exists.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  MODULE_HEADER,
  MODULE_SCOPE_REQUIRED,
  PRINT_JOBS_BASE_PATH,
} from './index.ts';

const SESSION = 's3ss10n-of-a-human-admin';
const PRINTING = 'printing';

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

/** A client scoped to the printing module, over a fetch that records and always says `ok`. */
function scoped(answer: unknown = { ok: true, data: {} }): {
  base: ErploraClient;
  client: ErploraClient;
  calls: Call[];
} {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({
      url,
      method: String(init.method),
      headers: init.headers as Record<string, string>,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    });
    return { status: 200, headers: { get: () => 'application/json' }, json: async () => answer };
  }) as unknown as typeof fetch;
  const transport = new HttpWsTransport({
    baseUrl: 'http://hub',
    fetchImpl,
    // Exactly what `apps/web/src/lib/runtime.ts` injects: the shell owns the credential and the
    // module never sees it. That is the entire point of routing through the SDK.
    headers: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': SESSION }),
  });
  const base = new ErploraClient(transport);
  return { base, client: base.forModule(PRINTING), calls };
}

test('hub#1108: the print surface carries the shell session — the module never touches the token', async () => {
  const { client, calls } = scoped({ ok: true, data: { jobId: 'j1', status: 'pending' } });

  const result = await client.printQueue.retry('j1');

  assert.deepEqual(result, { jobId: 'j1', status: 'pending' });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `http://hub${PRINT_JOBS_BASE_PATH}/j1/retry`);
  assert.equal(calls[0].method, 'POST');
  assert.equal(
    calls[0].headers['X-Hub-Session'],
    SESSION,
    'the session travels because the SHELL put it there, not because the module read it',
  );
  assert.equal(
    calls[0].headers[MODULE_HEADER],
    PRINTING,
    'the call names the module it acts for: that is what the `printer` capability gate reads',
  );
});

// ⚠️ The getter is `printQueue`, NOT `print`: `erplora.print(req)` is the published call every
// module uses to QUEUE a document (the shell bolts it onto this same client instance in
// `apps/web/src/main.ts`). Taking that name would have broken printing in every installed module.
test('hub#1108: an unscoped client has NO print surface — naming yourself is not optional', () => {
  const client = new ErploraClient(new HttpWsTransport({ baseUrl: '' }));
  assert.throws(
    () => client.printQueue,
    (e: unknown) => e instanceof ErploraError && e.code === MODULE_SCOPE_REQUIRED,
    'the recovery gestures are reachable only through `forModule(<id>)`',
  );
});

test('hub#1108: the surface is TWO routes and nothing else', async () => {
  const { client, calls } = scoped();
  const print = client.printQueue;

  // 1. The method LIST is pinned. Adding `request(path)`, `fetch(url)` or any other escape hatch
  //    turns this red — the only mechanical way to keep the surface from silently becoming a
  //    generic proxy to the core.
  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(print))
    .filter((n) => n !== 'constructor')
    .sort();
  assert.deepEqual(methods, ['discard', 'retry']);

  // 2. Every URL the surface can produce lands under ONE prefix.
  await print.retry('j1');
  await print.discard('j2');
  await print.discard('j3', 'de una sesión de QA');

  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('http://hub', '')}`),
    [
      'POST /api/print/jobs/j1/retry',
      'POST /api/print/jobs/j2/discard',
      'POST /api/print/jobs/j3/discard',
    ],
  );
  for (const call of calls) {
    assert.ok(
      call.url.startsWith(`http://hub${PRINT_JOBS_BASE_PATH}/`),
      `the surface must never leave its prefix: ${call.url}`,
    );
    assert.equal(call.headers[MODULE_HEADER], PRINTING);
  }

  // 3. Discarding without a reason sends NO body: closing a row without an essay stays a
  //    legitimate gesture, and an empty string is not the same thing as "I did not say".
  assert.equal(calls[1].body, undefined);
  assert.deepEqual(calls[2].body, { reason: 'de una sesión de QA' });
});

test('hub#1108: a jobId that would climb out of the prefix never leaves the process', async () => {
  const { client } = scoped();
  const print = client.printQueue;

  // `fetch` NORMALISES the URL: `/api/print/jobs/../../settings/retry` is sent as
  // `/api/settings/retry`. So a `jobId` pasted into a path is not a cosmetic problem — it is the
  // generic proxy, arriving by the back door. And the `jobId` is chosen by whoever queued the job,
  // which makes this the one id in the surface an attacker actually controls.
  const escapes = ['..', '../stations', 'a/b', '%2e%2e%2f', 'j1?x=1', 'j1#frag', '', ' ', 'a'.repeat(65)];
  for (const bad of escapes) {
    for (const call of [() => print.retry(bad), () => print.discard(bad)]) {
      await assert.rejects(
        call,
        (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
        `\`${bad}\` must be refused as a jobId`,
      );
    }
  }
});
