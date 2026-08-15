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
  EVENTS_BASE_PATH,
  FLOWS_BASE_PATH,
  HttpWsTransport,
  MODULE_HEADER,
  MODULE_SCOPE_REQUIRED,
  RELEASE_REVOKED,
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
    'schema',
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
  await flows.schema();

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
      'GET /api/hub/flows/schema',
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

test('hub#716: the editor ASKS the hub for the flow contract instead of carrying a copy', async () => {
  // The editor is a module installed from the marketplace and updated on its own clock (hub#516),
  // so a schema baked into its bundle is a photo of whatever core it was built against. What the
  // hub answers is what the hub ENFORCES — including the version, so the editor can say «this hub
  // is older than what you are drawing» rather than producing a document that gets refused.
  const contract = {
    schema_version: 1,
    core_version: '1.2.3',
    schema: { $id: 'https://erplora.com/schemas/flow.schema.json', type: 'object' },
  };
  const { client, calls } = scoped({ ok: true, data: contract });

  const served = await client.flows.schema();

  assert.deepEqual(served, contract);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `http://hub${FLOWS_BASE_PATH}/schema`);
  assert.equal(calls[0].method, 'GET');
  assert.equal(calls[0].headers[MODULE_HEADER], EDITOR, 'same gate as the rest of the surface');
});

// ─────────────────────────────────────────────────────────────────────────────
// hub#715 — the event catalogue the editor's data picker is built from.
//
// Same discipline as the flows surface and for the same reason: one method per route, no method
// that takes a path, module-scoped so the `manage_flows` gate has something to read. What an event
// carries is the shape of the business, and it is not something every installed module may read.
// ─────────────────────────────────────────────────────────────────────────────

test('hub#715: the event catalogue is module-scoped, like the kernel it feeds', () => {
  const client = new ErploraClient(new HttpWsTransport({ baseUrl: '' }));
  assert.throws(
    () => client.events,
    (e: unknown) => e instanceof ErploraError && e.code === MODULE_SCOPE_REQUIRED,
    'an unscoped client cannot read what the business events carry',
  );
});

test('hub#715: the surface is one route, and every id it can paste in one is checked', async () => {
  const { client, calls } = scoped({ ok: true, data: { event_name: 'sale.completed', fields: [] } });
  const events = client.events;

  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(events))
    .filter((n) => n !== 'constructor')
    .sort();
  assert.deepEqual(
    methods,
    // The dead-letter half arrived with hub#953; its own routes are pinned further down.
    ['dead', 'deadCount', 'discard', 'list', 'retry', 'retryAll', 'shape', 'trace'],
    'adding an escape hatch here turns this red on purpose',
  );

  await events.shape('sale.completed');
  await events.shape('hub.whatsapp.message_received', { limit: 3 });

  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('http://hub', '')}`),
    [
      'GET /api/hub/events/shape?name=sale.completed',
      'GET /api/hub/events/shape?name=hub.whatsapp.message_received&limit=3',
    ],
  );
  for (const call of calls) {
    assert.ok(call.url.startsWith(`http://hub${EVENTS_BASE_PATH}`));
    assert.equal(call.headers[MODULE_HEADER], EDITOR, 'the call names the module the gate reads');
    assert.equal(call.headers['X-Hub-Session'], SESSION, 'the SHELL owns the session, as always');
  }

  // The name travels in a query string rather than a path segment, but it is still checked: a
  // surface that accepts anything is one path-building change away from being a proxy.
  const before = calls.length;
  for (const bad of ['', '   ', '../secrets', 'a/b', 'a'.repeat(200), '1leading']) {
    await assert.rejects(
      () => events.shape(bad),
      (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
      `\`${bad}\` must be refused as an event name`,
    );
  }
  assert.equal(calls.length, before, 'not one of those became an HTTP request');
});

test('hub#823: the catalogue LISTS what this hub emits, so the picker stops being hand-written', async () => {
  // Until now `shape(name)` was the only way in and it needs the name first, so the flow editor
  // seeded its «when this happens» dropdown from a list typed into the module (`trigger-catalog.ts`,
  // flows#8). A hand-written list ages on its own and — the part that cannot be fixed by editing it
  // — can never offer an event this hub really emits that nobody thought to add.
  const catalogue = [
    { name: 'sale.completed', declared_by: ['sales'], last_seen_at: '2026-08-13T10:00:00Z' },
    // No `last_seen_at`: declared by an installed module, never yet emitted here. It is still a
    // legitimate trigger — a shop that has not sold anything yet may still automate the first sale.
    { name: 'appointments.appointment.created', declared_by: ['appointments'] },
    // No `declared_by`: seen in the outbox but its module is gone. The name is real, so it is
    // offered — the picker is what decides how to word it.
    { name: 'legacy.thing_happened', declared_by: [] },
  ];
  const { client, calls } = scoped({ ok: true, data: catalogue });

  const served = await client.events.list();

  assert.deepEqual(served, catalogue);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `http://hub${EVENTS_BASE_PATH}`, 'no query, no path segment');
  assert.equal(calls[0].method, 'GET');
  assert.equal(calls[0].headers[MODULE_HEADER], EDITOR, 'same `manage_flows` gate as `shape`');
  assert.equal(calls[0].headers['X-Hub-Session'], SESSION, 'the SHELL owns the session, as always');
});

test('hub#715: «no examples yet» reaches the editor as data, not as an error', async () => {
  // With a ninety-day retention (hub#699) an infrequent event has no surviving sample. That is a
  // 200 with `samples: 0` — a 404 would have the editor telling the owner the event does not
  // exist, about their own business.
  const { client } = scoped({
    ok: true,
    data: { event_name: 'shop.refund_issued', declared_by: ['shop'], samples: 0, fields: [] },
  });

  const shape = await client.events.shape('shop.refund_issued');

  assert.equal(shape.samples, 0);
  assert.deepEqual(shape.fields, []);
  assert.deepEqual(shape.declared_by, ['shop']);
});

// ─────────────────────────────────────────────────────────────────────────────
// hub#953 — the dead-letter queue, typed, so `ERPlora/flows#20` can draw the tray.
//
// The engine has been finished and operable over HTTP since hub#660: what died, with its payload,
// its error and its attempts; retry one, retry the lot, discard, trace. None of it was reachable
// through this surface, so the only person who could see a business event that never happened was
// one who knew how to `curl`. These six methods are the whole gap.
//
// Same discipline as the two surfaces above, and the same reason: one method per route, no method
// that takes a path, module-scoped so the `manage_flows` gate has something to read — and here the
// gate matters MORE than it does for the catalogue, because a dead-letter carries the whole payload
// and `retry` re-runs somebody else's command with that module's authority (hub#686).
// ─────────────────────────────────────────────────────────────────────────────

/** A dead-letter as the tray meets it: an invoice that never reached VeriFactu. */
const A_DEAD_LETTER = {
  id: 'e1a2b3c4',
  event_name: 'sale.closed',
  module_id: 'sales',
  user_id: 'cashier-1',
  payload: { invoice_id: 'F2-1', total: '12.10' },
  last_error: 'verifactu.records.ingest_invoice: permission_denied',
  attempts: 8,
  depth: 1,
  created_at: '2026-08-09T10:00:00+00:00',
  failure_kind: '',
  retryable: true,
};

test('hub#953: the six dead-letter gestures are six routes, and the surface is still not a proxy', async () => {
  const { client, calls } = scoped({ ok: true, data: [] });
  const events = client.events;

  // The method LIST is pinned, exactly as it is for the flows surface: an escape hatch added here
  // would hand a generic core proxy to every module the owner grants `manage_flows`.
  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(events))
    .filter((n) => n !== 'constructor')
    .sort();
  assert.deepEqual(methods, [
    'dead',
    'deadCount',
    'discard',
    'list',
    'retry',
    'retryAll',
    'shape',
    'trace',
  ]);

  await events.dead();
  await events.deadCount();
  await events.trace(A_DEAD_LETTER.id);
  await events.retry(A_DEAD_LETTER.id);
  await events.discard(A_DEAD_LETTER.id);
  await events.retryAll();

  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('http://hub', '')}`),
    [
      'GET /api/hub/events/dead',
      'GET /api/hub/events/dead/count',
      `GET /api/hub/events/${A_DEAD_LETTER.id}/trace`,
      `POST /api/hub/events/${A_DEAD_LETTER.id}/retry`,
      `POST /api/hub/events/${A_DEAD_LETTER.id}/discard`,
      // «Retry all» is THIS hub's queue and takes no argument, exactly like the endpoint: there is
      // no id, no filter and no way to name another tenant's rows.
      'POST /api/hub/events/retry-all',
    ],
  );
  for (const call of calls) {
    assert.ok(call.url.startsWith(`http://hub${EVENTS_BASE_PATH}`), `${call.url} escaped the prefix`);
    assert.equal(call.headers[MODULE_HEADER], EDITOR, 'the call names the module the gate reads');
    assert.equal(call.headers['X-Hub-Session'], SESSION, 'the SHELL owns the session, as always');
  }
});

test('hub#953: an id that would climb out of the prefix never becomes a request', async () => {
  const { client, calls } = scoped({ ok: true, data: null });
  const events = client.events;

  for (const bad of ['', '   ', '../../settings', 'a/b', 'a.b', '%2e%2e', 'a?x=1', 'a#f', 'a'.repeat(80)]) {
    for (const gesture of [
      () => events.retry(bad),
      () => events.discard(bad),
      () => events.trace(bad),
    ]) {
      await assert.rejects(
        gesture,
        (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
        `\`${bad}\` must be refused as an event id`,
      );
    }
  }
  assert.equal(calls.length, 0, 'not one of those left the process');
});

test('hub#953: the tray can tell a row it must NOT offer «Retry» for, before pressing anything', async () => {
  // The screen must not draw a button that cannot work (hub#827): a dead-letter whose flow release
  // was withdrawn comes back with `retryable: false` and the reason, so flows#20 can offer what
  // WOULD help — grant the permission again and run the flow — instead of a loop with no exit.
  const revoked = {
    ...A_DEAD_LETTER,
    id: 'e9f8d7c6',
    failure_kind: RELEASE_REVOKED,
    retryable: false,
  };
  const { client } = scoped({ ok: true, data: [A_DEAD_LETTER, revoked] });

  const queue = await client.events.dead();

  assert.equal(queue.length, 2);
  assert.equal(queue[0].retryable, true);
  assert.equal(queue[1].retryable, false);
  assert.equal(queue[1].failure_kind, RELEASE_REVOKED);
  // The payload arrives verbatim: it is what lets an operator tell a lost invoice from noise, and
  // it is exactly why this queue sits behind the capability and not behind «an admin is logged in».
  assert.deepEqual(queue[0].payload, { invoice_id: 'F2-1', total: '12.10' });
});

test('hub#953: a retry the runtime REFUSES arrives as a refusal, never as a promise it kept', async () => {
  // `outbox.rs` covers this at the engine
  // (`a_revoked_dead_letter_refuses_the_retry_instead_of_promising_one`): the row answers `409`
  // with its `failure_kind` rather than going back to `pending` to die again for the same reason.
  // What this pins is that the refusal survives the SDK — a resolved promise here would have
  // flows#20 telling an owner their invoice was re-sent when nothing moved.
  const { client } = scoped({
    ok: false,
    error: {
      code: RELEASE_REVOKED,
      message: 'this dead-letter cannot be replayed: the authorisation that produced it was withdrawn',
    },
  });

  await assert.rejects(
    () => client.events.retry(A_DEAD_LETTER.id),
    (e: unknown) => e instanceof ErploraError && e.code === RELEASE_REVOKED,
    'the tray has to be able to say WHY, which means reading the code',
  );
});

test('hub#955: discarding can say WHY, and the reason is the only thing the body carries', async () => {
  // `discarded_at` and `discarded_by` already survived the click; the reason did not, so the only
  // reading a closed row supported was «somebody discarded this». The tray asks for it, and the
  // hub writes it down — the author still comes from the session, so it is NOT in this body.
  const { client, calls } = scoped({
    ok: true,
    data: {
      id: A_DEAD_LETTER.id,
      status: 'discarded',
      discarded_by: 'hub_user:admin-1',
      discard_reason: 'duplicada: la factura se registró a mano',
    },
  });

  const closed = await client.events.discard(
    A_DEAD_LETTER.id,
    'duplicada: la factura se registró a mano',
  );
  assert.equal(closed.discard_reason, 'duplicada: la factura se registró a mano');

  // And it stays OPTIONAL: the call the surface shipped with (hub#953) sends no body at all,
  // rather than an empty reason a hub older than this would have to know to ignore.
  await client.events.discard(A_DEAD_LETTER.id);

  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('http://hub', '')}`),
    [
      `POST /api/hub/events/${A_DEAD_LETTER.id}/discard`,
      `POST /api/hub/events/${A_DEAD_LETTER.id}/discard`,
    ],
    'the reason changes the body, never the route',
  );
  assert.deepEqual(
    calls.map((c) => c.body),
    [{ reason: 'duplicada: la factura se registró a mano' }, undefined],
    'one field and no other: `discarded_by` is the session, not an argument',
  );
});

test('hub#953: the count is a number the badge can render, and retryAll says how many moved', async () => {
  const { client: counter } = scoped({ ok: true, data: { count: 3 } });
  assert.equal((await counter.events.deadCount()).count, 3);

  const { client: sweeper } = scoped({ ok: true, data: { retried: 2 } });
  assert.equal((await sweeper.events.retryAll()).retried, 2);
});

test('hub#953: a hub older than these routes leaves the methods ABSENT, so the screen can say so', () => {
  // The SDK travels WITH the hub (the shell hands the module its client), so «this hub is older
  // than the surface» reads as «the method is not there» — the same probe flows#8 already does for
  // `events.list` (`ui/lib/event-catalog.ts`). Pinning that the methods are ordinary, enumerable
  // prototype members is what keeps that probe honest: a getter that throws, or a Proxy that
  // answers everything, would make `typeof …dead === 'function'` a lie on an old hub.
  const { client } = scoped();
  const proto = Object.getPrototypeOf(client.events);
  for (const name of ['dead', 'deadCount', 'retry', 'discard', 'retryAll', 'trace']) {
    const descriptor = Object.getOwnPropertyDescriptor(proto, name) ?? { value: undefined };
    assert.equal(
      typeof descriptor.value,
      'function',
      `${name} must be a plain prototype method a module can probe for, not a getter`,
    );
    assert.equal(
      typeof (client.events as unknown as Record<string, unknown>)[name],
      'function',
      `\`typeof client.events.${name} === 'function'\` is the probe a module writes`,
    );
  }
});
