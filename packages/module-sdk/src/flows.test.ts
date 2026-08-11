// hub#714 — the DECLARED way a module reaches the automation kernel (`/api/hub/flows*`).
//
// The visual editor is a module (pm#110) and the SDK had no way in: `query`/`command` speak to the
// dispatcher, and flows are core REST on purpose (ADR-0283 §9). What a module *could* do was read
// the session token out of `localStorage` and `fetch` the door itself — same document, same origin,
// no sandbox. That works only while the user is an admin and dies the day the shell moves the
// session into an httpOnly cookie.
//
// So the surface is explicit, typed, module-scoped — and DELIBERATELY NOT a proxy. These tests are
// what stops it from becoming one: the method list is pinned, every URL it can produce is pinned to
// one prefix, and an id that would climb out of that prefix is refused before the request leaves.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ErploraClient,
  ErploraError,
  FLOWS_BASE_PATH,
  HttpWsTransport,
  MODULE_HEADER,
  MODULE_SCOPE_REQUIRED,
} from './index.ts';

const SESSION = 's3ss10n-of-a-human-admin';
const EDITOR = 'flows_editor';

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

/** A client scoped to the editor module, over a fetch that records and always says `ok`. */
function scoped(answer: unknown = { ok: true, data: [] }): {
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
  return { base, client: base.forModule(EDITOR), calls };
}

test('hub#714: the flows surface carries the shell session — the module never touches the token', async () => {
  const { client, calls } = scoped({ ok: true, data: [{ id: 'f1', name: 'Welcome' }] });

  const flows = await client.flows.list();

  assert.deepEqual(flows, [{ id: 'f1', name: 'Welcome' }]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `http://hub${FLOWS_BASE_PATH}`);
  assert.equal(calls[0].method, 'GET');
  assert.equal(
    calls[0].headers['X-Hub-Session'],
    SESSION,
    'the session travels because the SHELL put it there, not because the module read it',
  );
  assert.equal(
    calls[0].headers[MODULE_HEADER],
    EDITOR,
    'the call names the module it acts for: that is what the capability gate reads',
  );
});

test('hub#714: an unscoped client has NO flows surface — naming yourself is not optional', () => {
  const client = new ErploraClient(new HttpWsTransport({ baseUrl: '' }));
  assert.throws(
    () => client.flows,
    (e: unknown) => e instanceof ErploraError && e.code === MODULE_SCOPE_REQUIRED,
    'the kernel is reachable only through `forModule(<id>)`',
  );
});

test('hub#714: the surface is the FROZEN §9 route table and nothing else', async () => {
  const { client, calls } = scoped({ ok: true, data: null });
  const flows = client.flows;

  // 1. The method LIST is pinned. Adding `request(path)`, `fetch(url)` or any other escape hatch
  //    turns this red — which is the only mechanical way to keep the surface from silently
  //    becoming a generic proxy to the core.
  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(flows))
    .filter((n) => n !== 'constructor')
    .sort();
  assert.deepEqual(methods, [
    'approvals',
    'approve',
    'create',
    'deleteSecret',
    'get',
    'getRun',
    'grants',
    'list',
    'putSecret',
    'reject',
    'remove',
    'replaceGrants',
    'run',
    'runs',
    'secrets',
    'update',
  ]);

  // 2. Every URL the surface can produce lands under ONE prefix, and it is the frozen table.
  const doc = { name: 'Welcome', definition: { schema_version: 1, steps: [] } };
  await flows.list();
  await flows.create(doc);
  await flows.get('f1');
  await flows.update('f1', doc);
  await flows.remove('f1');
  await flows.grants('f1');
  await flows.replaceGrants('f1', []);
  await flows.run('f1', { total: 1 });
  await flows.runs('f1', { limit: 10, before: '2026-08-11T00:00:00Z' });
  await flows.getRun('r1');
  await flows.approvals('pending');
  await flows.approve('a1');
  await flows.reject('a1', { reason: 'no' });
  await flows.secrets();
  await flows.putSecret('API_KEY', 'sk-live-42');
  await flows.deleteSecret('API_KEY');

  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('http://hub', '')}`),
    [
      'GET /api/hub/flows',
      'POST /api/hub/flows',
      'GET /api/hub/flows/f1',
      'PUT /api/hub/flows/f1',
      'DELETE /api/hub/flows/f1',
      'GET /api/hub/flows/f1/grants',
      'PUT /api/hub/flows/f1/grants',
      'POST /api/hub/flows/f1/run',
      'GET /api/hub/flows/f1/runs?limit=10&before=2026-08-11T00%3A00%3A00Z',
      'GET /api/hub/flows/runs/r1',
      'GET /api/hub/flows/approvals?status=pending',
      'POST /api/hub/flows/approvals/a1/approve',
      'POST /api/hub/flows/approvals/a1/reject',
      'GET /api/hub/flows/secrets',
      'PUT /api/hub/flows/secrets/API_KEY',
      'DELETE /api/hub/flows/secrets/API_KEY',
    ],
  );
  for (const call of calls) {
    assert.ok(
      call.url.startsWith(`http://hub${FLOWS_BASE_PATH}`),
      `the surface must never leave its prefix: ${call.url}`,
    );
    assert.equal(call.headers[MODULE_HEADER], EDITOR);
  }
});

test('hub#714: an id that would climb out of the prefix never leaves the process', async () => {
  const { client, calls } = scoped();
  const flows = client.flows;

  // `fetch` NORMALISES the URL: `/api/hub/flows/../../settings` is sent as `/api/settings`. So an
  // id pasted into a path is not a cosmetic problem — it is the generic proxy, arriving by the back
  // door. Every id is checked here, before a request exists.
  const escapes = ['..', '../secrets', 'a/b', '%2e%2e%2f', 'f1?x=1', 'f1#frag', '', ' ', 'a'.repeat(65)];
  for (const bad of escapes) {
    for (const call of [
      () => flows.get(bad),
      () => flows.update(bad, { name: 'x', definition: {} }),
      () => flows.remove(bad),
      () => flows.grants(bad),
      () => flows.replaceGrants(bad, []),
      () => flows.run(bad),
      () => flows.runs(bad),
      () => flows.getRun(bad),
      () => flows.approve(bad),
      () => flows.reject(bad),
    ]) {
      await assert.rejects(
        call,
        (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
        `\`${bad}\` must be refused as an id`,
      );
    }
  }

  // A secret name is UPPER_SNAKE_CASE in the runtime (`flows/secrets.rs`), and it is read back as
  // `{{secret.NAME}}`: a name with a dot or a slash is a different thing entirely.
  for (const bad of ['api_key', 'API-KEY', '../API_KEY', 'API.KEY', '1KEY', '']) {
    await assert.rejects(
      () => flows.putSecret(bad, 'v'),
      (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
    );
    await assert.rejects(
      () => flows.deleteSecret(bad),
      (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
    );
  }

  assert.equal(calls.length, 0, 'not one of those became an HTTP request');
});

test('hub#714: the capability refusal arrives with its code, so the editor can ask for the grant', async () => {
  const fetchImpl = (async () => ({
    status: 403,
    headers: { get: () => 'application/json' },
    json: async () => ({
      ok: false,
      error: { code: 'capability_denied', message: 'requiere la capability `manage_flows`' },
    }),
  })) as unknown as typeof fetch;
  const client = new ErploraClient(new HttpWsTransport({ baseUrl: '', fetchImpl })).forModule(EDITOR);

  await assert.rejects(
    () => client.flows.list(),
    (e: unknown) => e instanceof ErploraError && e.code === 'capability_denied',
    'a bare «error» would leave the editor with nothing to tell the owner to do',
  );
});

test('hub#714: scoping does not fork the client — query/command still go to the dispatcher', async () => {
  const { client, calls } = scoped({ ok: true, data: [{ id: 'p1' }] });

  await client.query('inventory.products.list');

  assert.equal(calls[0].url, 'http://hub/api/query');
  assert.equal(
    calls[0].headers['X-Hub-Session'],
    SESSION,
    'the scoped client is the same client: one transport, one session, one event channel',
  );
});

test('hub#714: the scoped client still sees what the shell hung on the singleton', () => {
  const { base } = scoped();
  // `apps/web/src/main.ts` bolts `print` and `loadSlot` onto the ONE client instance after
  // building it, and every module calls them (`erplora.print(...)`, `erplora.loadSlot(...)`).
  // A scope that were a fresh `new ErploraClient(...)` would silently lose both, and the failure
  // would show up as «this module cannot print» in a shop, not here.
  (base as unknown as { print: () => string }).print = () => 'printed';
  (base as unknown as { loadSlot: () => string }).loadSlot = () => 'slotted';

  const scopedClient = base.forModule(EDITOR) as unknown as {
    print: () => string;
    loadSlot: () => string;
  };

  assert.equal(scopedClient.print(), 'printed');
  assert.equal(scopedClient.loadSlot(), 'slotted');
  assert.ok(base.forModule(EDITOR) instanceof ErploraClient, 'a scope is still a client');
});

test('hub#714: forModule refuses an empty id instead of sending an anonymous call', () => {
  const { base } = scoped();
  for (const bad of ['', '   ']) {
    assert.throws(
      () => base.forModule(bad),
      (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
    );
  }
});
