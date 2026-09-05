// Tests del SDK con transportes mock inyectables (sin red, sin Tauri).
// node:test + tsx (sin dependencias extra). Correr: pnpm -F @erplora/module-sdk test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  HttpWsTransport,
  type ElevationAsk,
  ErploraClient,
  ErploraError,
  createClient,
  IpcBridgeTransport,
  LocalNetworkPermissionDeniedError,
  LOCAL_NETWORK_PERMISSION_DENIED,
  SERVER_UNAVAILABLE,
  eurosToCents,
  centsToEuros,
  majorToMinor,
  minorToMajor,
  dataTableLabels,
  QUANTITY_SCALE,
  toMicro,
  fromMicro,
  parseQuantity,
  formatQuantity,
  onGrid,
} from './index.ts';

// The barrel re-exports the quantity contract (ADR-0147) from `./quantity.ts`. Asserting the
// symbols HERE — through `./index.ts`, not through `./quantity.ts` — is what pins the re-export
// specifier: this runner is `node:test` over ESM (`--experimental-transform-types`), which demands
// a fully specified relative path. Drop the `.ts` from the barrel's `from './quantity.ts'` and the
// whole file stops resolving. `quantity.test.ts` cannot catch that: it imports the module directly.
test('the barrel re-exports the quantity contract (ADR-0147)', () => {
  assert.equal(QUANTITY_SCALE, 1_000_000);
  assert.equal(toMicro(1.5), 1_500_000);
  assert.equal(fromMicro(1_500_000), 1.5);
  assert.equal(parseQuantity('1,5'), 1_500_000);
  assert.equal(formatQuantity(1_500_000), '1.5');
  assert.equal(onGrid(1_500_000, 500_000), true);
});

test('dataTableLabels traduce todo el chrome compartido de las tablas', () => {
  const es = dataTableLabels('es-ES');
  const en = dataTableLabels('en-GB');
  const fallback = dataTableLabels();
  assert.equal(es.columns, 'Columnas');
  assert.equal(es.rowsPerPage, 'Filas por página');
  assert.equal(es.recordPlural, 'registros');
  assert.equal(fallback.columns, 'Columnas');
  assert.equal(en.columns, 'Columns');
  assert.deepEqual(Object.keys(es), Object.keys(en));
});

// ── HttpWsTransport: query/command desenvuelven el sobre {ok,data} ───────────

test('HttpWsTransport.query hace POST /api/query y desenvuelve data', async () => {
  const calls: Array<{ url: string; body: unknown }> = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({ url, body: JSON.parse(init.body as string) });
    return { json: async () => ({ ok: true, data: [{ id: '1', name: 'Café' }] }) };
  }) as unknown as typeof fetch;

  const t = new HttpWsTransport({ baseUrl: 'http://h', fetchImpl });
  const rows = await t.query('inventory.products.list', { hub_id: 'h1' });

  assert.equal(calls[0].url, 'http://h/api/query');
  assert.deepEqual(calls[0].body, { name: 'inventory.products.list', params: { hub_id: 'h1' } });
  assert.deepEqual(rows, [{ id: '1', name: 'Café' }]);
});

test('HttpWsTransport.command envía {name,payload}', async () => {
  let sent: unknown;
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    sent = JSON.parse(init.body as string);
    return { json: async () => ({ ok: true, data: { ok: true } }) };
  }) as unknown as typeof fetch;

  const t = new HttpWsTransport({ baseUrl: '', fetchImpl });
  await t.command('inventory.products.create', { name: 'Té' });
  assert.deepEqual(sent, { name: 'inventory.products.create', payload: { name: 'Té' } });
});

test('un sobre {ok:false} lanza ErploraError con el code del server', async () => {
  const fetchImpl = (async () => ({
    json: async () => ({ ok: false, error: { code: 'permission_denied', message: 'no' } }),
  })) as unknown as typeof fetch;

  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('x.y'),
    (e: unknown) => e instanceof ErploraError && e.code === 'permission_denied',
  );
});

test('requires_elevation carries the missing permission through to the caller (hub#360)', async () => {
  // The dispatcher names the permission a manager would have to approve. It must survive the
  // envelope as a FIELD: the dialog of hub#363 has to name it and hub#361 has to re-check it —
  // neither may parse it out of the message.
  const fetchImpl = (async () => ({
    json: async () => ({
      ok: false,
      error: {
        code: 'requires_elevation',
        message: 'requires elevation: `sales.take_payment` needs approval from a manager',
        permission: 'sales.take_payment',
      },
    }),
  })) as unknown as typeof fetch;

  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('sales.sale.take_payment'),
    (e: unknown) =>
      e instanceof ErploraError &&
      e.code === 'requires_elevation' &&
      e.permission === 'sales.take_payment',
  );
});

test('a flat permission_denied carries no permission (it is not an offer to elevate)', async () => {
  const fetchImpl = (async () => ({
    json: async () => ({ ok: false, error: { code: 'permission_denied', message: 'no' } }),
  })) as unknown as typeof fetch;

  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('x.y'),
    (e: unknown) => e instanceof ErploraError && e.permission === undefined,
  );
});

test('headers() se inyectan en cada POST (auth X-Hub-Id, etc.)', async () => {
  let hdrs: Record<string, string> = {};
  const fetchImpl = (async (_u: string, init: RequestInit) => {
    hdrs = init.headers as Record<string, string>;
    return { json: async () => ({ ok: true, data: null }) };
  }) as unknown as typeof fetch;

  const t = new HttpWsTransport({ fetchImpl, headers: () => ({ 'X-Hub-Id': 'h1' }) });
  await t.query('q');
  assert.equal(hdrs['X-Hub-Id'], 'h1');
  assert.equal(hdrs['Content-Type'], 'application/json');
});

// ── hub#782: a non-JSON / non-2xx answer from the proxy is an ErploraError, not a SyntaxError ─
//
// The hub's runtime ALWAYS answers JSON — even its 4xx domain refusal travels in an envelope with a
// `code`. The proxy in front of it answers HTML (a 502 when the container OOMs at exit 137, hub#759;
// any deploy/restart window). Before this fix `post()` called `res.json()` without checking either,
// so a downed hub surfaced as a raw, code-less `SyntaxError: Unexpected token '<'` — not an
// `ErploraError`, so no module could orient by `code` and the HTML of the error page leaked through.

/** A `fetch` that answers `status` + `contentType` + `body` (the three things `post()` must check). */
function htmlishFetch(status: number, contentType: string, body: string): typeof fetch {
  return (async () => ({
    ok: false,
    status,
    headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? contentType : null) },
    json: async () => JSON.parse(body), // explodes for HTML — that is the whole point
  })) as unknown as typeof fetch;
}

test('hub#782: a 502 text/html from the proxy is ErploraError(server_unavailable), not a SyntaxError', async () => {
  const fetchImpl = htmlishFetch(502, 'text/html; charset=utf-8', '<!DOCTYPE html><html>bad gateway</html>');
  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.query('inventory.products.list'),
    (e: unknown) =>
      e instanceof ErploraError &&
      e.code === SERVER_UNAVAILABLE &&
      // The HTML of the proxy's error page must NOT leak: the cashier sees a message, never a trace.
      !String(e.message).includes('<') &&
      !String(e.message).includes('DOCTYPE'),
  );
});

test('hub#782: a response that IS JSON-shaped but reports a non-JSON content-type is transport error', async () => {
  // A misconfigured proxy that wraps even a good payload in text/plain would slip past a `res.ok`
  // guard; the content-type is what flags it as not the runtime's envelope.
  const fetchImpl = htmlishFetch(200, 'text/plain', '{"ok":true,"data":1}');
  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('x.y'),
    (e: unknown) => e instanceof ErploraError && e.code === SERVER_UNAVAILABLE,
  );
});

test('hub#782: a body that is not JSON even with an application/json content-type is wrapped, not thrown raw', async () => {
  // Defense in depth: some proxies/CDNs rewrite content-type but the body is still HTML.
  const fetchImpl = htmlishFetch(200, 'application/json', '<html>still not json</html>');
  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.query('q'),
    (e: unknown) =>
      e instanceof ErploraError && e.code === SERVER_UNAVAILABLE && !String(e.message).includes('<'),
  );
});

test('hub#782: a network-level fetch failure (TypeError) is wrapped as server_unavailable', async () => {
  const fetchImpl = (async () => {
    throw new TypeError('Failed to fetch');
  }) as unknown as typeof fetch;
  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.query('q'),
    (e: unknown) =>
      e instanceof ErploraError && e.code === SERVER_UNAVAILABLE && e.message !== 'Failed to fetch',
  );
});

test('hub#782: a 4xx domain refusal still flows through as its own code (NOT transport error)', async () => {
  // The runtime's domain refusals travel INSIDE a JSON envelope with a `code` — permission_denied,
  // requires_elevation, … They are NOT a transport failure, even when HTTP-status is 4xx. This is
  // the test that pins why the guard keys on Content-Type, not on `res.ok`.
  const fetchImpl = (async () => ({
    ok: false,
    status: 403,
    headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => ({ ok: false, error: { code: 'permission_denied', message: 'no' } }),
  })) as unknown as typeof fetch;
  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('x.y'),
    (e: unknown) => e instanceof ErploraError && e.code === 'permission_denied',
  );
});

// ── HttpWsTransport: WS de eventos (solo push) ──────────────────────────────

class FakeWs {
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  static last: FakeWs | undefined;
  close = () => {};
  constructor(public url: string) {
    FakeWs.last = this;
  }
}

test('subscribe abre el WS lazy y enruta eventos por nombre', () => {
  const t = new HttpWsTransport({
    baseUrl: 'http://h',
    WebSocketImpl: FakeWs as unknown as typeof WebSocket,
  });
  const seen: unknown[] = [];
  const unsub = t.subscribe('sale.completed', (p) => seen.push(p));

  assert.equal(FakeWs.last?.url, 'ws://h/ws');
  // Llega un evento de otro tipo → ignorado; el nuestro → entregado.
  FakeWs.last!.onmessage!({ data: JSON.stringify({ event: 'other', payload: 1 }) });
  FakeWs.last!.onmessage!({ data: JSON.stringify({ event: 'sale.completed', payload: { total: 9 } }) });
  assert.deepEqual(seen, [{ total: 9 }]);

  unsub();
  FakeWs.last!.onmessage!({ data: JSON.stringify({ event: 'sale.completed', payload: { total: 1 } }) });
  assert.equal(seen.length, 1, 'tras unsub no se reciben más');
});

// ── HttpWsTransport: push por SSE (hub#19) ──────────────────────────────────

class FakeEventSource {
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  static last: FakeEventSource | undefined;
  close = () => {};
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
}

test('push:sse abre EventSource(/api/events) y enruta eventos por nombre', () => {
  const t = new HttpWsTransport({
    baseUrl: 'http://h',
    push: 'sse',
    EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
  });
  const seen: unknown[] = [];
  const unsub = t.subscribe('sale.completed', (p) => seen.push(p));

  // SSE, no WS: el endpoint es /api/events sobre http.
  assert.equal(FakeEventSource.last?.url, 'http://h/api/events');
  // Mismo wire que el WS: {name|event, payload}. Otro tipo → ignorado; el nuestro → entregado.
  FakeEventSource.last!.onmessage!({ data: JSON.stringify({ name: 'other', payload: 1 }) });
  FakeEventSource.last!.onmessage!({ data: JSON.stringify({ name: 'sale.completed', payload: { total: 7 } }) });
  assert.deepEqual(seen, [{ total: 7 }]);

  unsub();
  FakeEventSource.last!.onmessage!({ data: JSON.stringify({ name: 'sale.completed', payload: { total: 2 } }) });
  assert.equal(seen.length, 1, 'tras unsub no se reciben más');
});

test("createClient('http+sse') selecciona el push por SSE", () => {
  const es: string[] = [];
  class ES {
    onmessage = null;
    close = () => {};
    constructor(public url: string) {
      es.push(url);
    }
  }
  const c = createClient('http+sse', {
    http: { baseUrl: 'http://h', EventSourceImpl: ES as unknown as typeof EventSource },
  });
  c.on('x', () => {});
  assert.deepEqual(es, ['http://h/api/events']);
});

// ── hub#504: the event channel asks for a credential ────────────────────────

/** A fake socket with the `onopen` an authenticated channel needs, and a record of what it sent. */
class FakeAuthWs {
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onopen: (() => void) | null = null;
  sent: string[] = [];
  closed = false;
  static last: FakeAuthWs | undefined;
  close = () => {
    this.closed = true;
  };
  send = (data: string) => {
    this.sent.push(data);
  };
  constructor(public url: string) {
    FakeAuthWs.last = this;
  }
}

/** Lets an awaited credential settle before asserting. */
const settle = () => new Promise((r) => setTimeout(r, 0));

test('the socket presents the credential the shell hands it, in the FIRST FRAME (hub#504)', async () => {
  let asked = 0;
  const t = new HttpWsTransport({
    baseUrl: 'http://h',
    WebSocketImpl: FakeAuthWs as unknown as typeof WebSocket,
    streamCredential: async () => `erpl_tkt_${++asked}`,
  });
  const seen: unknown[] = [];
  t.subscribe('sale.completed', (p) => seen.push(p));

  // Not in the URL: a credential in a URL is a credential in every access log on the way.
  assert.equal(FakeAuthWs.last?.url, 'ws://h/ws');
  assert.deepEqual(FakeAuthWs.last!.sent, [], 'nothing is sent before the socket is open');

  FakeAuthWs.last!.onopen!();
  await settle();
  assert.deepEqual(JSON.parse(FakeAuthWs.last!.sent[0]!), { type: 'auth', token: 'erpl_tkt_1' });

  // And it is still the same channel: domain events arrive exactly as before.
  FakeAuthWs.last!.onmessage!({
    data: JSON.stringify({ name: 'sale.completed', payload: { total: 9 } }),
  });
  assert.deepEqual(seen, [{ total: 9 }]);
});

test('every reconnect asks for a FRESH credential: the ticket is single use', async () => {
  let n = 0;
  const t = new HttpWsTransport({
    baseUrl: 'http://h',
    WebSocketImpl: FakeAuthWs as unknown as typeof WebSocket,
    streamCredential: async () => `erpl_tkt_${++n}`,
  });
  t.subscribe('sale.completed', () => {});
  FakeAuthWs.last!.onopen!();
  await settle();
  const first = JSON.parse(FakeAuthWs.last!.sent[0]!).token;

  // The socket drops and the transport reopens. Replaying the spent ticket would be refused by the
  // hub and the shell would go deaf without saying so.
  FakeAuthWs.last!.onclose!();
  await new Promise((r) => setTimeout(r, 1_100));
  FakeAuthWs.last!.onopen!();
  await settle();
  const second = JSON.parse(FakeAuthWs.last!.sent[0]!).token;

  assert.notEqual(first, second);
});

test('with no credential available the socket is closed instead of sitting there mute', async () => {
  const t = new HttpWsTransport({
    baseUrl: 'http://h',
    WebSocketImpl: FakeAuthWs as unknown as typeof WebSocket,
    // Nobody has logged in yet: there is no ticket to be had.
    streamCredential: async () => null,
  });
  t.subscribe('sale.completed', () => {});
  FakeAuthWs.last!.onopen!();
  await settle();
  assert.deepEqual(FakeAuthWs.last!.sent, []);
  assert.equal(FakeAuthWs.last!.closed, true);
});

test('with nobody logged in, the retry BACKS OFF instead of hammering the hub', async () => {
  // The shell wires its listeners at boot — before anybody has logged in — so "no credential yet"
  // is the normal state of the login screen, not an error. Retrying every second there would post
  // to the hub 60 times a minute for as long as the till sits idle.
  const delays: number[] = [];
  const realSetTimeout = globalThis.setTimeout;
  // Records the reconnect delay without ever firing it: the test drives the reconnects by hand.
  (globalThis as { setTimeout: unknown }).setTimeout = ((fn: () => void, ms: number) => {
    if (ms >= 500) {
      delays.push(ms);
      return 0;
    }
    return realSetTimeout(fn, ms);
  }) as typeof globalThis.setTimeout;

  try {
    const t = new HttpWsTransport({
      baseUrl: 'http://h',
      WebSocketImpl: FakeAuthWs as unknown as typeof WebSocket,
      streamCredential: async () => null,
    });
    t.subscribe('sale.completed', () => {});
    for (let i = 0; i < 3; i += 1) {
      FakeAuthWs.last!.onopen!();
      await settle();
      FakeAuthWs.last!.onclose!();
      // The scheduled reconnect never fires on its own here; open the next socket by hand.
      if (i < 2) t.subscribe(`x${i}`, () => {});
    }

    assert.ok(delays.length >= 2, `expected several reconnect delays, got ${delays.length}`);
    assert.ok(
      delays[delays.length - 1]! > delays[0]!,
      `the wait must grow: ${JSON.stringify(delays)}`,
    );
  } finally {
    (globalThis as { setTimeout: unknown }).setTimeout = realSetTimeout;
  }
});

test('a refusal from the channel is reported, not swallowed', async () => {
  const refusals: string[] = [];
  const t = new HttpWsTransport({
    baseUrl: 'http://h',
    WebSocketImpl: FakeAuthWs as unknown as typeof WebSocket,
    streamCredential: async () => 'erpl_tkt_x',
    onStreamRefused: (code, message) => refusals.push(`${code}:${message}`),
  });
  const asDomainEvent: unknown[] = [];
  t.subscribe('stream.error', (p) => asDomainEvent.push(p));
  t.subscribe('stream.ready', (p) => asDomainEvent.push(p));
  FakeAuthWs.last!.onopen!();
  await settle();

  FakeAuthWs.last!.onmessage!({
    data: JSON.stringify({
      type: 'stream.error',
      code: 'events.read_required',
      message: 'no reading',
    }),
  });
  FakeAuthWs.last!.onmessage!({ data: JSON.stringify({ type: 'stream.ready' }) });

  assert.deepEqual(refusals, ['events.read_required:no reading']);
  assert.deepEqual(asDomainEvent, [], 'a control frame is not a domain event');
});

test('SSE carries the credential in the query, because it has no first frame', async () => {
  const t = new HttpWsTransport({
    baseUrl: 'http://h',
    push: 'sse',
    EventSourceImpl: FakeEventSource as unknown as typeof EventSource,
    streamCredential: async () => 'erpl_tkt_sse',
  });
  t.subscribe('sale.completed', () => {});
  await settle();
  assert.equal(FakeEventSource.last?.url, 'http://h/api/events?ticket=erpl_tkt_sse');
});

// ── ErploraClient: hasPermission (solo UI) ──────────────────────────────────

test('hasPermission respeta wildcard y permisos namespaced', () => {
  const admin = new ErploraClient({} as never, { permissions: () => new Set(['*']) });
  assert.equal(admin.hasPermission('inventory.add_product'), true);

  const emp = new ErploraClient({} as never, {
    permissions: () => new Set(['inventory.view_product']),
  });
  assert.equal(emp.hasPermission('inventory.view_product'), true);
  assert.equal(emp.hasPermission('inventory.add_product'), false);
});

test('createClient http+ws construye un cliente con HttpWsTransport (ADR-0050: sin variante ipc)', () => {
  const c = createClient('http+ws', { http: { baseUrl: '' } });
  assert.ok(c instanceof ErploraClient);
});

// ── ErploraClient: moneda del hub + formateo (ADR-0059) ─────────────────────

test('currency usa el getter inyectado por el shell (normaliza a mayúsculas)', () => {
  const c = new ErploraClient({} as never, { currency: () => 'usd' });
  assert.equal(c.currency, 'USD');
});

test('currency degrada a EUR sin getter ni publicación global', () => {
  const prev = (globalThis as { __erploraCurrency?: string }).__erploraCurrency;
  delete (globalThis as { __erploraCurrency?: string }).__erploraCurrency;
  try {
    const c = new ErploraClient({} as never, {});
    assert.equal(c.currency, 'EUR');
  } finally {
    if (prev !== undefined) (globalThis as { __erploraCurrency?: string }).__erploraCurrency = prev;
  }
});

test('currency lee globalThis.__erploraCurrency cuando no hay getter (fallback del shell)', () => {
  const prev = (globalThis as { __erploraCurrency?: string }).__erploraCurrency;
  (globalThis as { __erploraCurrency?: string }).__erploraCurrency = 'gbp';
  try {
    const c = new ErploraClient({} as never, {});
    assert.equal(c.currency, 'GBP');
  } finally {
    if (prev === undefined) delete (globalThis as { __erploraCurrency?: string }).__erploraCurrency;
    else (globalThis as { __erploraCurrency?: string }).__erploraCurrency = prev;
  }
});

// ── ErploraClient: zona horaria del negocio (hub#731, hub#1022) ─────────────

test('timezone usa el getter inyectado por el shell (SIN normalizar: IANA es case-sensitive)', () => {
  const c = new ErploraClient({} as never, { timezone: () => 'Atlantic/Canary' });
  assert.equal(c.timezone, 'Atlantic/Canary');
});

test('timezone degrada a UTC sin getter ni publicación global', () => {
  const prev = (globalThis as { __erploraTimezone?: string }).__erploraTimezone;
  delete (globalThis as { __erploraTimezone?: string }).__erploraTimezone;
  try {
    const c = new ErploraClient({} as never, {});
    assert.equal(c.timezone, 'UTC');
  } finally {
    if (prev !== undefined) (globalThis as { __erploraTimezone?: string }).__erploraTimezone = prev;
  }
});

test('timezone lee globalThis.__erploraTimezone cuando no hay getter (fallback del shell)', () => {
  const prev = (globalThis as { __erploraTimezone?: string }).__erploraTimezone;
  (globalThis as { __erploraTimezone?: string }).__erploraTimezone = 'Europe/Lisbon';
  try {
    const c = new ErploraClient({} as never, {});
    assert.equal(c.timezone, 'Europe/Lisbon');
  } finally {
    if (prev === undefined) delete (globalThis as { __erploraTimezone?: string }).__erploraTimezone;
    else (globalThis as { __erploraTimezone?: string }).__erploraTimezone = prev;
  }
});

test('formatMoney convierte céntimos→unidades con la moneda del hub', () => {
  // Locale fijo para que el separador/símbolo sea determinista entre entornos.
  const c = new ErploraClient({} as never, { currency: () => 'USD' });
  assert.equal(c.formatMoney(123450, { locale: 'en-US' }), '$1,234.50');
  assert.equal(c.formatMoney(0, { locale: 'en-US' }), '$0.00');
});

test('formatAmount formatea unidades; opts.currency sobreescribe la del hub', () => {
  const c = new ErploraClient({} as never, { currency: () => 'EUR' });
  assert.equal(c.formatAmount(1234.5, { locale: 'en-US', currency: 'USD' }), '$1,234.50');
});

// hub#1090: CLDR deja sin agrupar los 4 dígitos en español (minimumGroupingDigits=2), pero la
// regla vinculante del CLAUDE.md raíz es la del sector (Odoo, Holded, glibc, Excel): agrupar
// SIEMPRE desde 4. Este formateador es el que usan los módulos de dinero vía
// `globalThis.erplora.formatMoney` — el que ejecuta el SHELL, así que arreglarlo aquí arregla
// las pantallas de módulo sin republicar módulos.
test('formatMoney agrupa los millares DESDE 4 dígitos también en es (hub#1090)', () => {
  // CLDR es separa cifra y € con un espacio INSEPARABLE (U+00A0), no un espacio normal.
  const c = new ErploraClient({} as never, { currency: () => 'EUR' });
  assert.equal(c.formatMoney(123456, { locale: 'es-ES' }), '1.234,56 €');
  assert.equal(c.formatMoney(1234567, { locale: 'es-ES' }), '12.345,67 €');
  assert.equal(c.formatAmount(1234.5, { locale: 'es-ES' }), '1.234,50 €');
});

// ── ADR-0196 §3: el SDK ya NO lleva canal WS local de hardware ──────────────────────────
//
// El único camino a la impresora es la app instalada (`IpcBridgeTransport` sobre `invoke`,
// in-process). Con el canal WS se van sus tres problemas de navegador: PNA (Private Network
// Access), mixed-content (una página https abriendo `ws://localhost`) y la clave pública con la
// que el bridge verificaba offline el token de emparejamiento.
//
// Se asertan las DOS mitades porque cada una sola miente. Que el símbolo desaparezca del barrel
// es el contrato hacia los módulos; que el hardware POR DEFECTO no abra nada es el comportamiento.
// Borrar solo el alias `WsBridgeTransport` dejando `BridgeClient` cableado en `peripherals`
// pasaría la primera y no habría retirado nada.

test('el barrel ya NO exporta el transporte WS de hardware (ADR-0196 §3)', async () => {
  const sdk = await import('./index.ts');
  for (const gone of ['WsBridgeTransport', 'BridgeClient', 'BRIDGE_DEFAULT_PORT']) {
    assert.equal(gone in sdk, false, `${gone} sigue exportado por el SDK`);
  }
  // Lo que SÍ sigue siendo contrato: la interfaz y el transporte de la app instalada.
  assert.equal('IpcBridgeTransport' in sdk, true);
});

/** Espía del `fetch` global: el WS-bridge sondeaba `http://localhost:12321/status` al detectar. */
async function withFetchSpy<T>(run: () => Promise<T>): Promise<{ result: T; urls: string[] }> {
  const urls: string[] = [];
  const real = globalThis.fetch;
  globalThis.fetch = (async (u: unknown) => {
    urls.push(String(u));
    throw new Error('ninguna llamada de red debería salir de aquí');
  }) as typeof fetch;
  try {
    return { result: await run(), urls };
  } finally {
    globalThis.fetch = real;
  }
}

test('sin la app instalada, detect() dice «offline» y NO sondea localhost', async () => {
  // `detect()` no puede rechazar: el módulo printing lo llama SIN try/catch
  // (`erp-printing-settings.ts → refreshBridge`), así que un rechazo aquí le rompe la pantalla
  // de ajustes entera en vez de enseñarle su estado «sin hardware».
  const c = new ErploraClient({} as never, {});
  const { result, urls } = await withFetchSpy(() => c.peripherals.detect());
  assert.deepEqual(result, { online: false });
  assert.deepEqual(urls, [], 'un navegador sin la app no llama a ningún puerto local');
});

// Cada operación que toca hardware, una a una: si alguna resolviera «bien» sin haber hecho nada,
// el TPV daría por impreso un tique que no ha salido. Fallar es la respuesta correcta.
const HARDWARE_OPS: Array<[string, (t: ErploraClient['peripherals']) => Promise<unknown>]> = [
  ['discoverPrinters', (t) => t.discoverPrinters()],
  ['getDevices', (t) => t.getDevices()],
  ['print', (t) => t.print('network:192.168.1.50:9100', 'receipt', { total: 100 })],
  ['testPrint', (t) => t.testPrint('network:192.168.1.50:9100')],
  ['openDrawer', (t) => t.openDrawer('network:192.168.1.50:9100')],
  ['setDeviceRole', (t) => t.setDeviceRole('aa:bb:cc:dd:ee:ff', 'receipt')],
];

for (const [name, run] of HARDWARE_OPS) {
  test(`sin la app instalada, ${name}() rechaza con \`hardware_unavailable\``, async () => {
    const c = new ErploraClient({} as never, {});
    await assert.rejects(
      () => run(c.peripherals),
      (e: unknown) => {
        // El código es lo estable: un módulo distingue «no hay hardware aquí» de «la impresora
        // no responde» por él, nunca leyendo el texto.
        assert.ok(e instanceof ErploraError, `${name} debe rechazar con ErploraError`);
        assert.equal(e.code, 'hardware_unavailable');
        return true;
      },
    );
  });
}

test('sin frase inyectada por el shell, el rechazo AÚN dice algo', async () => {
  // El shell inyecta la frase traducida; el SDK se queda con la inglesa del log. Lo que no puede
  // quedarse es sin mensaje: quien enseñe `error.message` pintaría un hueco.
  const c = new ErploraClient({} as never, {});
  await assert.rejects(
    () => c.peripherals.testPrint('network:192.168.1.50:9100'),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.ok(e.message.trim().length > 0, 'el rechazo por defecto necesita mensaje');
      return true;
    },
  );
});

test('notify() sin la app NO lanza: best-effort por contrato', async () => {
  // Una notificación que no sale no puede tumbar la comanda que la provocó (contrato de
  // `BridgeTransport.notify`), y los dos transportes que quedan lo cumplen igual.
  const c = new ErploraClient({} as never, {});
  await c.peripherals.notify('Nueva comanda', 'Mesa 4 · 3 platos');
});

test('createClient tampoco cablea el WS de hardware (ADR-0196 §3)', async () => {
  // La fábrica pasaba `new BridgeClient()` como periféricos: el WS entraba por aquí aunque el
  // shell eligiera bien su transporte.
  const c = createClient('http+ws', { http: { baseUrl: 'http://h' } });
  const { result, urls } = await withFetchSpy(() => c.peripherals.detect());
  assert.deepEqual(result, { online: false });
  assert.deepEqual(urls, []);
});

test('el transporte que inyecta el shell manda sobre el «sin hardware» por defecto', async () => {
  // El defecto es la degradación, no una pared: el shell de la app instalada sigue inyectando su
  // `IpcBridgeTransport` y ese es el que ven los módulos.
  const injected = { detect: async () => ({ online: true, version: '9.9' }) } as never;
  const c = new ErploraClient({} as never, {}, injected);
  assert.deepEqual(await c.peripherals.detect(), { online: true, version: '9.9' });
});

// ── hub#338: «no encuentro impresoras» ≠ «no me dejan buscarlas» ────────────────────────
//
// Las dos llegaban aquí como el MISMO array vacío, y son instrucciones opuestas para el usuario:
// «conecta una impresora» frente a «dale permiso a la app». El transporte de invoke ya recibe el
// outcome con su `status`; lo que se prueba aquí es que el consumidor pueda distinguirlos —
// resolver [] en el caso bloqueado sería exactamente el bug.

/** Shell Tauri de mentira: responde lo que se le diga a `erplora_discover_printers`. */
function fakeShell(discovery: unknown) {
  const calls: string[] = [];
  const tauri = {
    invoke: async (cmd: string) => {
      calls.push(cmd);
      if (cmd === 'erplora_discover_printers') return discovery;
      return {};
    },
    listen: async () => () => {},
  };
  return { transport: new IpcBridgeTransport(tauri), calls };
}

const A_PRINTER = {
  id: 'network:192.168.1.50:9100',
  name: 'Cocina',
  type: 'network',
  status: 'ready',
  paper_width: 80,
};

test('descubrimiento con permiso: devuelve la lista tal cual', async () => {
  const { transport } = fakeShell({ status: 'scanned', printers: [A_PRINTER] });
  assert.deepEqual(await transport.discoverPrinters(), [A_PRINTER]);
});

test('descubrimiento con permiso y sin impresoras: un CERO honesto, no un error', async () => {
  // Buscamos y no hay nada. Eso es una respuesta: el módulo enseña su estado vacío de siempre.
  const { transport } = fakeShell({ status: 'scanned', printers: [] });
  assert.deepEqual(await transport.discoverPrinters(), []);
});

test('descubrimiento SIN permiso: rechaza con un error propio en vez de resolver []', async () => {
  const { transport } = fakeShell({
    status: LOCAL_NETWORK_PERMISSION_DENIED,
    permission: 'android.permission.ACCESS_LOCAL_NETWORK',
  });

  await assert.rejects(
    () => transport.discoverPrinters(),
    (e: unknown) => {
      assert.ok(
        e instanceof LocalNetworkPermissionDeniedError,
        'el consumidor tiene que poder distinguirlo por tipo, no leyendo el texto',
      );
      assert.equal(e.code, LOCAL_NETWORK_PERMISSION_DENIED);
      assert.equal(e.permission, 'android.permission.ACCESS_LOCAL_NETWORK');
      return true;
    },
  );
});

test('un shell de escritorio VIEJO devuelve el array pelado y sus impresoras no se pierden', async () => {
  // La app de escritorio es un binario INSTALADO y la PWA se sirve del hub: pueden ir desfasados.
  // Leerle `.printers` a un array daría [] — esconder impresoras encontradas, la misma mentira
  // mirando al otro lado.
  const { transport } = fakeShell([A_PRINTER]);
  assert.deepEqual(await transport.discoverPrinters(), [A_PRINTER]);
});

test('un fallo CUALQUIERA del escaneo sigue siendo un Error normal', async () => {
  // Solo el permiso cambia de tipo: un fallo de hardware no debe mandar al usuario a los ajustes
  // del sistema a tocar un permiso que ya tiene. Se aserta contra el transporte que QUEDA tras
  // ADR-0196 §3 — la misma distinción que probaba el WS, ahora por la única puerta viva.
  const transport = new IpcBridgeTransport({
    invoke: async (cmd: string) => {
      if (cmd === 'erplora_discover_printers') throw new Error('impresora inalcanzable');
      return {};
    },
    listen: async () => () => {},
  });

  await assert.rejects(transport.discoverPrinters(), (e: unknown) => {
    assert.ok(e instanceof Error);
    assert.ok(!(e instanceof LocalNetworkPermissionDeniedError));
    return true;
  });
});

// ── hub#337: the permission is asked for whenever the LAN is about to be used ───────────
//
// Scanning was the only operation that asked. But a till hardly ever scans: the printer is
// assigned to a role once and remembered, so the everyday sequence on a fresh device is
// install → sell → print, with no discovery anywhere in it. The print then goes to a TCP socket
// on the LAN, which Android blocks below the API level: the socket times out, the ticket never
// comes out, and nothing is reported anywhere. Asking is idempotent on the native side — already
// granted means no dialog — so the cost of asking here is nothing and the cost of not asking is
// a till that silently stops printing.

const REACHES_THE_PRINTER: Array<[string, (t: IpcBridgeTransport) => Promise<unknown>]> = [
  // Discovery is the one that already asked (hub#338), kept here so the whole set of operations
  // that touch the LAN is asserted in one place — the SDK is where the asking lives, and a guard
  // that only exists in the shell's tests leaves the SDK free to drop it.
  ['erplora_discover_printers', (t) => t.discoverPrinters()],
  ['erplora_print', (t) => t.print('network:192.168.1.50:9100', 'receipt', { total: 100 })],
  ['erplora_test_print', (t) => t.testPrint('network:192.168.1.50:9100')],
  ['erplora_open_drawer', (t) => t.openDrawer('network:192.168.1.50:9100')],
];

for (const [command, run] of REACHES_THE_PRINTER) {
  test(`${command} asks for the local network permission before reaching the printer`, async () => {
    const { transport, calls } = fakeShell({ status: 'scanned', printers: [] });

    await run(transport);

    const asked = calls.indexOf('plugin:erplora-android|request_permissions');
    assert.notEqual(asked, -1, `${command} never asks for the permission it needs`);
    assert.ok(
      asked < calls.indexOf(command),
      `${command} talks to the printer before asking: ${JSON.stringify(calls)}`,
    );
  });
}

// ── hub#758: an operation asks ONLY for the permission it is about to use ───────────────
//
// The request used to carry no scope, and the plugin answered it by asking for its WHOLE batch:
// tapping «Re-scan» on a fresh Android popped the local-network dialog and then, out of nowhere,
// the notifications one. A permission that appears with no visible relation to what the user just
// did reads as opportunistic and gets denied — and a denied POST_NOTIFICATIONS is a kitchen that
// stops hearing orders. So the scope travels with every request: discovery and printing name the
// local network, and the notifications dialog belongs to the first flow that actually notifies.

function fakeShellRecordingPermissionArgs() {
  const requests: unknown[] = [];
  const tauri = {
    invoke: async (cmd: string, args?: unknown) => {
      if (cmd === 'plugin:erplora-android|request_permissions') requests.push(args);
      if (cmd === 'erplora_discover_printers') return { status: 'scanned', printers: [] };
      return {};
    },
    listen: async () => () => {},
  };
  return { transport: new IpcBridgeTransport(tauri), requests };
}

// Discovery is the one operation that looks at BOTH transports on Android — the LAN sweep and the
// bonded Bluetooth list (ADR-0204) — so it names both printer permissions. Still zero
// notifications: that dialog belongs to the flow that notifies.
test('discovery asks for the two printer permissions and nothing else (hub#758/hub#388)', async () => {
  const { transport, requests } = fakeShellRecordingPermissionArgs();

  await transport.discoverPrinters();

  assert.deepEqual(requests, [
    {
      permissions: [
        'android.permission.ACCESS_LOCAL_NETWORK',
        'android.permission.BLUETOOTH_CONNECT',
      ],
    },
  ]);
});

for (const [command, run] of REACHES_THE_PRINTER) {
  if (command === 'erplora_discover_printers') continue; // asserted above: discovery scans both transports
  test(`${command} to a network printer asks only for the local-network permission (hub#758)`, async () => {
    const { transport, requests } = fakeShellRecordingPermissionArgs();

    await run(transport);

    assert.deepEqual(requests, [{ permissions: ['android.permission.ACCESS_LOCAL_NETWORK'] }]);
  });
}

// A `bluetooth:{mac}` job leaves through RFCOMM, not the LAN (ADR-0204): asking for the network
// permission there would be the same out-of-context dialog hub#758 removed, pointing the other way.
const REACHES_A_BLUETOOTH_PRINTER: Array<[string, (t: IpcBridgeTransport) => Promise<unknown>]> = [
  ['erplora_print', (t) => t.print('bluetooth:AA:BB:CC:DD:EE:FF', 'receipt', { total: 100 })],
  ['erplora_test_print', (t) => t.testPrint('bluetooth:AA:BB:CC:DD:EE:FF')],
  ['erplora_open_drawer', (t) => t.openDrawer('bluetooth:AA:BB:CC:DD:EE:FF')],
];

for (const [command, run] of REACHES_A_BLUETOOTH_PRINTER) {
  test(`${command} to a bluetooth printer asks only for BLUETOOTH_CONNECT (hub#388)`, async () => {
    const { transport, requests } = fakeShellRecordingPermissionArgs();

    await run(transport);

    assert.deepEqual(requests, [{ permissions: ['android.permission.BLUETOOTH_CONNECT'] }]);
  });
}

test('notify asks only for the notifications permission — its own context, nothing else (hub#758)', async () => {
  const { transport, requests } = fakeShellRecordingPermissionArgs();

  await transport.notify('New order', 'Table 4');

  assert.deepEqual(requests, [{ permissions: ['android.permission.POST_NOTIFICATIONS'] }]);
});

test('a refused permission does not stop the till from trying to print', async () => {
  // A "no" is an answer, not a crash — and the user may have granted it in the system settings
  // since. Failing here would turn a permission the till does not strictly need on this Android
  // version into a till that cannot sell.
  const calls: string[] = [];
  const tauri = {
    invoke: async (cmd: string) => {
      calls.push(cmd);
      if (cmd === 'plugin:erplora-android|request_permissions') throw new Error('denied');
      return {};
    },
    listen: async () => () => {},
  };

  await new IpcBridgeTransport(tauri).print('network:192.168.1.50:9100', 'receipt', {});

  assert.ok(calls.includes('erplora_print'));
});

// ── La frontera EUROS ↔ CÉNTIMOS (ADR-0123) ─────────────────────────────────────────────
//
// El dinero es un INTEGER de céntimos, pero un humano teclea EUROS: un `<input step="0.01">`, un
// CSV con el catálogo del cliente. Esa conversión es una FRONTERA, y hasta ahora no existía en el
// SDK: cada Web Component se la escribía a mano. Los que no lo hicieron produjeron los bugs de ×100
// (un café de 2,20 € guardado como producto de 2 céntimos; un billete de 20 € registrado como 20
// céntimos). Ahora la frontera vive aquí, con el gemelo Rust en `guest_sdk::money::euros_to_cents`.
test('eurosToCents: lo que teclea un humano son EUROS', () => {
  assert.equal(eurosToCents('2.20'), 220);
  assert.equal(eurosToCents('50'), 5000);
  assert.equal(eurosToCents('0.01'), 1);
});

test('eurosToCents: el céntimo NO se pierde por la coma flotante', () => {
  // El bug clásico: 0.29 * 100 = 28.999999999999996 en IEEE-754 → sin Math.round, 28 céntimos.
  assert.equal(eurosToCents('0.29'), 29);
  assert.equal(eurosToCents('1.15'), 115);
});

test('eurosToCents: la basura entra como 0, no como NaN', () => {
  // Un CSV de cliente trae celdas vacías. Un NaN en una columna INTEGER es corrupción silenciosa.
  assert.equal(eurosToCents(''), 0);
  assert.equal(eurosToCents('abc'), 0);
  assert.equal(eurosToCents(undefined), 0);
});

test('centsToEuros: la vuelta, para rellenar un input de edición', () => {
  assert.equal(centsToEuros(220), '2.20');
  assert.equal(centsToEuros(5), '0.05');
  assert.equal(centsToEuros(0), '0.00');
  assert.equal(centsToEuros(undefined), '');
});

// ── La MONEDA define la escala, no una constante (ADR-0123 §7) ──────────────────────────
//
// El dinero viaja en UNIDADES MÍNIMAS, y cuántas hay en una unidad mayor **depende de la moneda**:
// EUR 2, **JPY 0**, KWD 3. El `/ 100` que estaba clavado aquí es un bug en cuanto un hub se pone en
// yenes — y la app es gratuita, así que se pondrá: mostraría 19,99 ¥ donde hay **1999 ¥**.
test('majorToMinor: lo que teclea un humano depende de SU moneda', () => {
  assert.equal(majorToMinor('19.99', 2), 1999); // EUR
  assert.equal(majorToMinor('1999', 0), 1999); // JPY: NO se multiplica por 100
  assert.equal(majorToMinor('1.999', 3), 1999); // KWD
});

test('minorToMajor: pintar tampoco divide siempre entre 100', () => {
  assert.equal(minorToMajor(1999, 2), 19.99);
  assert.equal(minorToMajor(1999, 0), 1999, 'en yenes NO se divide');
  assert.equal(minorToMajor(1999, 3), 1.999);
});

test('el mismo entero significa cosas distintas según la moneda', () => {
  // Es LA razón de todo esto: `1999` no significa nada sin su moneda.
  assert.equal(minorToMajor(1999, 2), 19.99); //   19,99 €
  assert.equal(minorToMajor(1999, 0), 1999); // 1999   ¥
});

test('el céntimo no se pierde por la coma flotante, sea cual sea la escala', () => {
  assert.equal(majorToMinor('0.29', 2), 29); // 0.29*100 = 28.999… en IEEE-754
  assert.equal(majorToMinor('1.005', 3), 1005);
});

test('eurosToCents sigue existiendo, y es majorToMinor con escala 2', () => {
  // Se conserva para los sitios donde la moneda es EUR POR CONTRATO (VeriFactu, fiscalidad ES).
  assert.equal(eurosToCents('2.20'), majorToMinor('2.20', 2));
});

// ── queryAll: TODAS las filas, paginando por dentro ──────────────────────────
//
// Por qué existe: el runtime tiene un tope duro por request (`MAX_LIMIT = 500`) y, si no le mandas
// `limit`, cae al `page_size` que declara el manifest (50 por defecto). Un TPV no quiere "una
// página": quiere TODOS sus productos, y un desplegable de IVA TODAS las categorías. La forma en
// que las vistas intentaban pedir eso era `query(name, { page_size: 200 })` — y `page_size` NO ES
// UN PARÁMETRO del runtime, así que se ignoraba en silencio y llegaban 50. Un restaurante con 80
// platos solo podía vender 50: los otros 30 no existían en el TPV.
//
// `queryAll` no lleva número mágico: itera limit/offset hasta agotar `total`.

/** Transporte que simula una query de lista de `total` filas, respetando limit/offset. */
function transporteDeLista(total: number, registro: unknown[] = []) {
  return {
    query: async (name: string, params?: Record<string, unknown>) => {
      registro.push({ name, ...params });
      const limit = Number(params?.limit ?? 50); // sin `limit` → page_size del manifest
      const offset = Number(params?.offset ?? 0);
      const rows = Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) => ({
        id: `p${offset + i}`,
      }));
      return { rows, total, limit, offset };
    },
    command: async () => ({}),
    subscribe: () => () => {},
  };
}

test('queryAll devuelve TODAS las filas: sin tope', async () => {
  const llamadas: Record<string, unknown>[] = [];
  const c = new ErploraClient(transporteDeLista(1234, llamadas));

  const rows = await c.queryAll<{ id: string }>('inventory.products.list');

  assert.equal(rows.length, 1234, 'un hub con 1234 productos los ve los 1234');
  assert.equal(rows[0].id, 'p0');
  assert.equal(rows[1233].id, 'p1233', 'la última fila también llega');
  assert.equal(llamadas.length, 2, 'una página para saber el total + una para pedirlo entero');
  assert.equal(llamadas[1].limit, 1234, 'pide el total EXACTO, no un número cableado a ojo');
});

test('queryAll no manda nunca `page_size` (no es un parámetro del runtime)', async () => {
  const llamadas: Record<string, unknown>[] = [];
  const c = new ErploraClient(transporteDeLista(10, llamadas));

  await c.queryAll('taxes.categories.list', { sort: 'name', dir: 'asc' });

  assert.equal(llamadas[0].page_size, undefined, 'page_size sería ignorado por el runtime');
  assert.equal(llamadas[0].sort, 'name', 'los filtros del llamador se conservan');
});

test('queryAll con `limit` explícito respeta ESE tope (el llamador manda)', async () => {
  const llamadas: Record<string, unknown>[] = [];
  const c = new ErploraClient(transporteDeLista(1000, llamadas));

  const rows = await c.queryAll('customers.list', { limit: 20, search: 'ana' });

  assert.equal(rows.length, 20, 'pidió 20 (typeahead): le llegan 20, no los 1000');
  assert.equal(llamadas.length, 1, 'un solo viaje: no hace falta ir a por el resto');
  assert.equal(llamadas[0].limit, 20);
});

test('queryAll cabe en un viaje si la primera página ya lo trae todo', async () => {
  const llamadas: unknown[] = [];
  const c = new ErploraClient(transporteDeLista(8, llamadas));
  assert.equal((await c.queryAll('taxes.categories.list')).length, 8);
  assert.equal(llamadas.length, 1, '8 categorías caben en la primera página: no hay segundo viaje');
});

test('queryAll con una lista vacía devuelve [] sin girar en vacío', async () => {
  const llamadas: unknown[] = [];
  const c = new ErploraClient(transporteDeLista(0, llamadas));
  assert.deepEqual(await c.queryAll('inventory.products.list'), []);
  assert.equal(llamadas.length, 1, 'un solo viaje, no un bucle infinito');
});

test('queryAll tolera una query que NO es de lista (devuelve el array tal cual)', async () => {
  const c = new ErploraClient({
    query: async () => [{ id: 'a' }, { id: 'b' }], // sin sobre {rows,total}
    command: async () => ({}),
    subscribe: () => () => {},
  });
  assert.deepEqual(await c.queryAll('taxes.rules.list'), [{ id: 'a' }, { id: 'b' }]);
});

// ── queryOptional: la optionalidad es del MÓDULO, no del contrato (ADR-0127) ─────────────────
//
// `sales` consulta `verifactu.records.by_invoice` SOLO si el hub tiene verifactu instalado. La
// forma antigua era `.catch(() => [])` — que se tragaba TODO: módulo ausente, pero también query
// renombrada, permiso denegado, handler roto. `queryOptional` perdona UNA sola cosa: la ausencia
// del módulo (código `module_not_installed`, que el runtime distingue de `query_not_found`).

function transporteQueFalla(code: string) {
  return {
    query: async () => { throw new ErploraError(code, `error ${code}`); },
    command: async () => ({}),
    subscribe: () => () => {},
  };
}

test('queryOptional devuelve undefined SOLO si el módulo no está instalado', async () => {
  const c = new ErploraClient(transporteQueFalla('module_not_installed'));
  assert.equal(await c.queryOptional('verifactu.records.by_invoice', { invoice_id: 'i1' }), undefined);
});

test('queryOptional NO se traga un contrato roto (query inexistente en módulo presente)', async () => {
  const c = new ErploraClient(transporteQueFalla('not_found'));
  await assert.rejects(() => c.queryOptional('verifactu.records.by_invoice'), (e) => {
    assert.ok(e instanceof ErploraError && e.code === 'not_found', 'el contrato roto EXPLOTA');
    return true;
  });
});

test('queryOptional NO se traga permisos ni fallos del handler', async () => {
  for (const code of ['permission_denied', 'invalid_payload', 'wasm', 'db']) {
    const c = new ErploraClient(transporteQueFalla(code));
    await assert.rejects(() => c.queryOptional('verifactu.records.by_invoice'), (e) => {
      assert.equal((e as ErploraError).code, code);
      return true;
    });
  }
});

test('queryOptional con el módulo presente devuelve los datos tal cual (desenvuelve la página)', async () => {
  const c = new ErploraClient({
    query: async () => ({ rows: [{ id: 'r1' }], total: 1, limit: 50, offset: 0 }),
    command: async () => ({}),
    subscribe: () => () => {},
  });
  assert.deepEqual(await c.queryOptional('verifactu.records.by_invoice'), [{ id: 'r1' }]);
});

test('queryOptional también trata module_inactive como ausencia (cascada ADR-0128)', async () => {
  // Un módulo DESACTIVADO (manual o arrastrado) equivale a ausente para un consumidor opcional:
  // el obligatorio nunca llega a preguntar, porque la cascada lo apagó junto a su dependencia.
  const c = new ErploraClient(transporteQueFalla('module_inactive'));
  assert.equal(await c.queryOptional('verifactu.records.by_invoice'), undefined);
});

// ── queryOptional/queryAllOptional short-circuit: absence must not cost a ROUND TRIP (hub#1211) ─
//
// Before this fix, `queryOptional` learned a module was absent by asking the transport ANYWAY and
// catching `module_not_installed` AFTER the request already happened. Every optional integration a
// hub does not have left one `POST /api/query` → 404 in the browser console PER CALL — `sales`
// asking `verifactu.records.by_invoice` on a hub with no VeriFactu logged a 404 on every sale
// (surfaced as hub#1121, `sales`→`modifiers`). The shell now injects `installedModules`, the live
// set of ACTIVE module ids (mirrors how `permissions`/`currency`/`timezone` are already injected);
// when it says the query's owning module (the segment before the first `.`) is absent, the SDK
// must never call the transport at all — this is a test that COUNTS REQUESTS, not one that only
// asserts on the returned value (that shape already passed before this defect and would keep
// passing after a fix that fixes nothing).

function transporteQueCuenta(respuesta: unknown = { rows: [], total: 0, limit: 50, offset: 0 }) {
  const calls: Array<{ name: string; params?: Record<string, unknown> }> = [];
  return {
    calls,
    transport: {
      query: async (name: string, params?: Record<string, unknown>) => {
        calls.push({ name, params });
        return respuesta;
      },
      command: async () => ({}),
      subscribe: () => () => {},
    },
  };
}

test('query_optional_does_not_travel_when_the_owner_module_is_absent_hub1211', async () => {
  const { transport, calls } = transporteQueCuenta();
  const c = new ErploraClient(transport, { installedModules: () => new Set(['sales']) });

  const result = await c.queryOptional('verifactu.records.by_invoice', { invoice_id: 'i1' });

  assert.equal(result, undefined, 'with verifactu not installed, the caller sees an absence');
  assert.equal(calls.length, 0, 'the SDK must NOT ask the transport to find that out');
});

test('query_all_optional_does_not_travel_when_the_owner_module_is_absent_hub1211', async () => {
  const { transport, calls } = transporteQueCuenta();
  const c = new ErploraClient(transport, { installedModules: () => new Set(['sales']) });

  const result = await c.queryAllOptional('verifactu.records.by_invoice');

  assert.equal(result, undefined);
  assert.equal(calls.length, 0, 'queryAllOptional short-circuits exactly like queryOptional');
});

test('query_optional_still_travels_when_the_owner_module_is_installed_hub1211', async () => {
  const { transport, calls } = transporteQueCuenta({ rows: [{ id: 'r1' }], total: 1, limit: 50, offset: 0 });
  const c = new ErploraClient(transport, { installedModules: () => new Set(['verifactu']) });

  const result = await c.queryOptional('verifactu.records.by_invoice');

  assert.deepEqual(result, [{ id: 'r1' }]);
  assert.equal(calls.length, 1, 'the module IS installed: the request has to travel for real');
});

test('query_optional_still_travels_when_the_installed_set_is_not_known_yet_hub1211', async () => {
  // Before the shell's first `GET /api/modules` resolves (or with an old host that never passes
  // `installedModules`), the SDK cannot tell "absent" from "not known yet" — and guessing "absent"
  // would be the SYMMETRIC regression: a real query silently skipped.
  const c = new ErploraClient(transporteQueFalla('module_not_installed'), {
    installedModules: () => undefined,
  });

  assert.equal(await c.queryOptional('verifactu.records.by_invoice'), undefined);
});

test('a_renamed_query_still_explodes_hub1211', async () => {
  // The module IS present (the short-circuit does not apply) but its query was renamed/removed:
  // that is a broken contract, not an absence, and it has to explode exactly as before.
  const c = new ErploraClient(transporteQueFalla('not_found'), {
    installedModules: () => new Set(['verifactu']),
  });

  await assert.rejects(() => c.queryOptional('verifactu.records.by_invoice'), (e) => {
    assert.ok(e instanceof ErploraError && e.code === 'not_found', 'the broken contract STILL explodes');
    return true;
  });
});

test('query_optional_never_short_circuits_the_core_namespace_hub1211', async () => {
  // `hub.*` is the runtime's RESERVED namespace (ADR-0192, `hub_users.rs::CORE_NAMESPACE`): the
  // core serves it before the registry, it is never an installed module, and the runtime never
  // answers `module_not_installed` for it. `installedModules` lists modules, so `hub` is never in
  // it — a short-circuit keyed on that set alone would turn every `queryOptional('hub.…')` into a
  // silent `undefined`, which is the false-absence the whole fix exists to avoid.
  const { transport, calls } = transporteQueCuenta({ rows: [{ id: 'row' }], total: 1, limit: 1, offset: 0 });
  const c = new ErploraClient(transport, { installedModules: () => new Set(['sales']) });

  const result = await c.queryOptional('hub.setup.status');

  assert.deepEqual(result, [{ id: 'row' }], 'the core answered and the caller sees it');
  assert.equal(calls.length, 1, 'the core namespace ALWAYS travels: nothing can prove it absent');
});

test('query_all_optional_never_short_circuits_the_core_namespace_hub1211', async () => {
  const { transport, calls } = transporteQueCuenta({ rows: [{ id: 'row' }], total: 1, limit: 1, offset: 0 });
  const c = new ErploraClient(transport, { installedModules: () => new Set(['sales']) });

  const result = await c.queryAllOptional('hub.users.list');

  assert.deepEqual(result, [{ id: 'row' }]);
  assert.equal(calls.length, 1, 'same rule for queryAllOptional');
});

// ── queryAllOptional: the WHOLE set of an OPTIONAL module (ERPlora/sales#186) ────────────────
//
// The two halves this needs already existed, and neither one alone is what a POS asks for:
//
//  · `queryAll` brings the whole set (two trips at most) but EXPLODES when the owner module is not
//    installed — so it cannot be used for an ADR-0127 integration.
//  · `queryOptional` tolerates the absence but returns ONE PAGE: `/api/query` on a query with a
//    `list` block answers `execute_query_page`, and with no `limit` the size is the manifest's
//    `page_size` — 50. A hair salon with 60 services could only sell 50 of them, silently.
//
// `queryAllOptional` is the pair: the whole set, `undefined` when the module is absent. Anything
// else still explodes — a renamed query, a denied permission or a broken handler are broken
// contracts, not absences.

test('queryAllOptional brings EVERY row, not the first page', async () => {
  const calls: Record<string, unknown>[] = [];
  const c = new ErploraClient(transporteDeLista(137, calls));

  const rows = await c.queryAllOptional<{ id: string }>('services.services.list');

  assert.equal(rows?.length, 137, 'a salon with 137 services sells all 137');
  assert.equal(rows?.[136].id, 'p136', 'the last row arrives too');
  assert.equal(calls.length, 2, 'one page to learn the total + one to ask for it whole');
  assert.equal(calls[1].limit, 137, 'asks for the EXACT total, no hardcoded cap');
});

test('queryAllOptional returns undefined when the owner module is not installed', async () => {
  const c = new ErploraClient(transporteQueFalla('module_not_installed'));
  assert.equal(await c.queryAllOptional('services.services.list'), undefined);
});

test('queryAllOptional also treats module_inactive as absence (ADR-0128 cascade)', async () => {
  const c = new ErploraClient(transporteQueFalla('module_inactive'));
  assert.equal(await c.queryAllOptional('services.services.list'), undefined);
});

test('queryAllOptional does NOT swallow a broken contract, a permission or a handler failure', async () => {
  for (const code of ['not_found', 'permission_denied', 'invalid_payload', 'wasm', 'db']) {
    const c = new ErploraClient(transporteQueFalla(code));
    await assert.rejects(() => c.queryAllOptional('services.services.list'), (e) => {
      assert.equal((e as ErploraError).code, code, 'a broken contract EXPLODES, it is not an absence');
      return true;
    });
  }
});

test('queryAllOptional never sends `page_size` and keeps the caller filters', async () => {
  const calls: Record<string, unknown>[] = [];
  const c = new ErploraClient(transporteDeLista(10, calls));

  await c.queryAllOptional('services.categories.list', { sort: 'name', dir: 'asc' });

  assert.equal(calls[0].page_size, undefined, 'the runtime would ignore `page_size`');
  assert.equal(calls[0].sort, 'name');
});

test('queryAllOptional with an explicit `limit` respects THAT cap (the caller rules)', async () => {
  const calls: Record<string, unknown>[] = [];
  const c = new ErploraClient(transporteDeLista(1000, calls));

  const rows = await c.queryAllOptional('customers.list', { limit: 20, search: 'ana' });

  assert.equal(rows?.length, 20);
  assert.equal(calls.length, 1, 'a single trip: nothing else was asked for');
});

test('queryAllOptional tells an EMPTY module apart from an ABSENT one', async () => {
  // `[]` = installed with nothing to offer (the POS shows no service tab); `undefined` = not
  // installed. Collapsing the two is how a caller stops being able to explain what it is seeing.
  const c = new ErploraClient(transporteDeLista(0));
  assert.deepEqual(await c.queryAllOptional('services.services.list'), []);
});

// ── commandOptional: la puerta OPCIONAL para ESCRIBIR (hub#1428, simétrica a queryOptional) ──
//
// `combos` (`depends_on: []`) quiere dar de alta un producto en `inventory` desde su propio
// selector, SOLO si `inventory` está instalado en este hub — igual que `queryOptional` deja leer
// una integración que puede faltar. `commandOptional` perdona UNA sola cosa: la ausencia del
// módulo dueño (`module_not_installed`/`module_inactive`, el mismo par que distingue el runtime
// para las queries desde ADR-0127/0128). Todo lo demás EXPLOTA como en `command()`: un command
// inexistente en un módulo presente, un permiso denegado, un handler roto, o el fallo de
// transporte que hub#906 convierte en `UnknownOutcomeError` (sigue siendo `SERVER_UNAVAILABLE`,
// nunca una ausencia).

function transporteQueFallaCommand(code: string) {
  return {
    query: async () => ({}),
    command: async () => { throw new ErploraError(code, `error ${code}`); },
    subscribe: () => () => {},
  };
}

test('commandOptional devuelve undefined SOLO si el módulo no está instalado', async () => {
  const c = new ErploraClient(transporteQueFallaCommand('module_not_installed'));
  assert.equal(await c.commandOptional('inventory.products.create', { name: 'Corte' }), undefined);
});

test('commandOptional también trata module_inactive como ausencia (cascada ADR-0128)', async () => {
  const c = new ErploraClient(transporteQueFallaCommand('module_inactive'));
  assert.equal(await c.commandOptional('inventory.products.create'), undefined);
});

test('commandOptional NO se traga un contrato roto (command inexistente en módulo presente)', async () => {
  const c = new ErploraClient(transporteQueFallaCommand('command_not_found'));
  await assert.rejects(() => c.commandOptional('inventory.products.create'), (e) => {
    assert.ok(e instanceof ErploraError && e.code === 'command_not_found', 'el contrato roto EXPLOTA');
    return true;
  });
});

test('commandOptional NO se traga permisos ni fallos del handler', async () => {
  for (const code of ['permission_denied', 'invalid_payload', 'wasm', 'db']) {
    const c = new ErploraClient(transporteQueFallaCommand(code));
    await assert.rejects(() => c.commandOptional('inventory.products.create'), (e) => {
      assert.equal((e as ErploraError).code, code);
      return true;
    });
  }
});

test('commandOptional NO se traga el verdict de un fallo de transporte (hub#906)', async () => {
  // El hub murió a mitad de la petición: la escritura PUEDE haber comprometido antes de perder la
  // respuesta. `command()` lo convierte en `UnknownOutcomeError` (código SERVER_UNAVAILABLE, NO
  // uno de los dos que `commandOptional` perdona) — tragárselo como ausencia le mentiría al
  // llamante «no se escribió nada» cuando la verdad es «no lo sabemos».
  const c = new ErploraClient(transporteQueFallaCommand(SERVER_UNAVAILABLE));
  await assert.rejects(() => c.commandOptional('inventory.products.create'), (e) => {
    assert.ok(e instanceof ErploraError && e.code === SERVER_UNAVAILABLE);
    assert.equal((e as { outcomeUnknown?: boolean }).outcomeUnknown, true, 'sigue siendo el verdict de hub#906');
    return true;
  });
});

test('commandOptional con el módulo presente devuelve el resultado tal cual', async () => {
  const c = new ErploraClient({
    query: async () => ({}),
    command: async () => ({ id: 'p1', name: 'Corte' }),
    subscribe: () => () => {},
  });
  assert.deepEqual(await c.commandOptional('inventory.products.create', { name: 'Corte' }), {
    id: 'p1',
    name: 'Corte',
  });
});

// ── commandOptional short-circuit: una ausencia PROBADA no cuesta un viaje (hub#1211/hub#1428) ─
//
// Mismo mecanismo que `queryOptional`: cuando `installedModules` (inyectado por el shell) PRUEBA
// que el módulo dueño está ausente, el SDK no debe llamar NUNCA al transporte — así el intento de
// escritura ni siquiera se dispara, y `undefined` significa siempre «no se escribió nada», jamás
// «se escribió y no lo sabemos» (no hay ventana de carrera: el runtime resuelve la ausencia DENTRO
// de la misma petición que la escritura, antes de tocar la BD — nunca en un chequeo aparte).

function transporteDeComandoQueCuenta(respuesta: unknown = { ok: true }) {
  const calls: Array<{ name: string; payload?: Record<string, unknown> }> = [];
  return {
    calls,
    transport: {
      query: async () => ({}),
      command: async (name: string, payload?: Record<string, unknown>) => {
        calls.push({ name, payload });
        return respuesta;
      },
      subscribe: () => () => {},
    },
  };
}

test('command_optional_does_not_travel_when_the_owner_module_is_absent_hub1428', async () => {
  const { transport, calls } = transporteDeComandoQueCuenta();
  const c = new ErploraClient(transport, { installedModules: () => new Set(['combos']) });

  const result = await c.commandOptional('inventory.products.create', { name: 'Corte' });

  assert.equal(result, undefined, 'con inventory no instalado, el llamante ve una ausencia');
  assert.equal(calls.length, 0, 'el SDK no debe intentar la escritura para averiguarlo');
});

test('command_optional_still_travels_when_the_owner_module_is_installed_hub1428', async () => {
  const { transport, calls } = transporteDeComandoQueCuenta({ id: 'p1' });
  const c = new ErploraClient(transport, { installedModules: () => new Set(['inventory']) });

  const result = await c.commandOptional('inventory.products.create', { name: 'Corte' });

  assert.deepEqual(result, { id: 'p1' });
  assert.equal(calls.length, 1, 'el módulo SÍ está: la escritura tiene que viajar de verdad');
});

test('command_optional_still_travels_when_the_installed_set_is_not_known_yet_hub1428', async () => {
  const c = new ErploraClient(transporteQueFallaCommand('module_not_installed'), {
    installedModules: () => undefined,
  });
  assert.equal(await c.commandOptional('inventory.products.create'), undefined);
});

test('a_command_not_found_still_explodes_hub1428', async () => {
  // El módulo SÍ está presente (no hay corto-circuito) pero el command no existe: contrato roto,
  // no ausencia — tiene que explotar exactamente como antes.
  const c = new ErploraClient(transporteQueFallaCommand('command_not_found'), {
    installedModules: () => new Set(['inventory']),
  });
  await assert.rejects(() => c.commandOptional('inventory.products.create'), (e) => {
    assert.ok(e instanceof ErploraError && e.code === 'command_not_found', 'el contrato roto SIGUE explotando');
    return true;
  });
});

test('command_optional_never_short_circuits_the_core_namespace_hub1428', async () => {
  // `hub.*` nunca está "ausente" (ADR-0192): `installedModules` nunca lo lista, así que un
  // corto-circuito ciego a ese conjunto convertiría todo `commandOptional('hub.…')` en un
  // `undefined` silencioso — la ausencia falsa que el fix entero existe para evitar.
  const { transport, calls } = transporteDeComandoQueCuenta({ ok: true });
  const c = new ErploraClient(transport, { installedModules: () => new Set(['sales']) });

  const result = await c.commandOptional('hub.set_pin', { pin: '1234' });

  assert.deepEqual(result, { ok: true }, 'el core respondió y el llamante lo ve');
  assert.equal(calls.length, 1, 'el namespace del core SIEMPRE viaja: nada puede probarlo ausente');
});

// ── hub#363: the approval dialog's TRANSPORT half ────────────────────────────
//
// The runtime has said `requires_elevation` since hub#360 and has minted approvals since hub#361,
// but nothing on the client ever asked for one. These tests pin WHERE that ask lives — here, in
// the one place every module's `erplora.command()` already passes through — and the two things it
// must never do: send the elevated attempt twice, or offer a dialog to a caller that cannot type.

/** A `fetch` that answers a scripted queue of envelopes and records what it was asked. */
function scriptedFetch(replies: unknown[]): {
  fetchImpl: typeof fetch;
  calls: Array<{ url: string; body: { name?: string; payload?: unknown }; headers: Record<string, string> }>;
} {
  const calls: Array<{ url: string; body: { name?: string; payload?: unknown }; headers: Record<string, string> }> = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({
      url,
      body: JSON.parse(init.body as string),
      headers: { ...(init.headers as Record<string, string>) },
    });
    const reply = replies[calls.length - 1];
    if (reply instanceof Error) throw reply;
    return { json: async () => reply };
  }) as unknown as typeof fetch;
  return { fetchImpl, calls };
}

const REFUSED = {
  ok: false,
  error: {
    code: 'requires_elevation',
    message: 'requires elevation: `till.void_sale` needs approval from a manager',
    permission: 'till.void_sale',
  },
};
const WENT_THROUGH = { ok: true, data: { voided: true } };

test('hub#363: a refusal a manager can approve asks the shell for a PIN and retries with the token', async () => {
  const { fetchImpl, calls } = scriptedFetch([REFUSED, WENT_THROUGH]);
  const asks: ElevationAsk[] = [];
  const t = new HttpWsTransport({
    fetchImpl,
    headers: () => ({ 'X-Hub-Id': 'h1' }),
    elevationApprover: async (ask) => {
      asks.push(ask);
      return 'tok-abc';
    },
  });

  assert.deepEqual(await t.command('till.sale.void', { sale_id: 's1' }), { voided: true });

  // The dialog was told WHAT it is asking approval for — command, the exact payload, and the
  // permission the runtime named as a field (hub#360). None of it parsed out of a sentence.
  assert.equal(asks.length, 1);
  assert.equal(asks[0].command, 'till.sale.void');
  assert.deepEqual(asks[0].payload, { sale_id: 's1' });
  assert.equal(asks[0].permission, 'till.void_sale');

  // Two calls: the one that was refused and the one the approval bought. The retry is the SAME
  // action — a different payload would not match the grant's fingerprint — plus the header, and it
  // keeps the shell's own headers (without X-Hub-Id the runtime would not even route it).
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1].body, { name: 'till.sale.void', payload: { sale_id: 's1' } });
  assert.equal(calls[1].headers['X-Elevation-Token'], 'tok-abc');
  assert.equal(calls[1].headers['X-Hub-Id'], 'h1');
  // …and the FIRST one carried no token: an approval is asked for after the refusal, never before.
  assert.equal(calls[0].headers['X-Elevation-Token'], undefined);
});

test('hub#363: a cashier who closes the dialog gets the refusal they already had, unchanged', async () => {
  // `null` = nobody approved. The caller must see exactly what it saw before this feature existed,
  // so a module that already handles `requires_elevation` keeps working.
  const { fetchImpl, calls } = scriptedFetch([REFUSED]);
  const t = new HttpWsTransport({ fetchImpl, elevationApprover: async () => null });

  await assert.rejects(
    () => t.command('till.sale.void', { sale_id: 's1' }),
    (e: unknown) =>
      e instanceof ErploraError && e.code === 'requires_elevation' && e.permission === 'till.void_sale',
  );
  assert.equal(calls.length, 1, 'nothing was sent without an approval');
});

test('hub#363: a flat permission_denied never opens a dialog', async () => {
  // hub#361 made an API key's refusal FLAT — no `permission` field — precisely so it is not offered
  // a dialog it cannot follow. A capture that treated every 403 alike would undo that: a machine
  // would sit waiting on a PIN nobody is there to type.
  for (const code of ['permission_denied', 'module_not_installed', 'invalid_payload']) {
    const { fetchImpl, calls } = scriptedFetch([{ ok: false, error: { code, message: 'no' } }]);
    let asked = false;
    const t = new HttpWsTransport({
      fetchImpl,
      elevationApprover: async () => {
        asked = true;
        return 'tok';
      },
    });
    await assert.rejects(() => t.command('till.sale.void'), (e: unknown) => (e as ErploraError).code === code);
    assert.equal(asked, false, `\`${code}\` must not be read as an offer to elevate`);
    assert.equal(calls.length, 1);
  }
});

test('hub#363: a query is never elevated — only actions are', async () => {
  // The runtime keeps queries refusing flat on purpose (`permissions::check_command` is the command
  // gate, and only that): an approval exists to ATTRIBUTE an action to the manager who allowed it,
  // and a PIN that unlocked a report would leave no such trace. Capturing on the query path would
  // build exactly that door on the client.
  const { fetchImpl } = scriptedFetch([REFUSED]);
  let asked = false;
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async () => {
      asked = true;
      return 'tok';
    },
  });
  await assert.rejects(() => t.query('till.sales.list'), (e: unknown) => e instanceof ErploraError);
  assert.equal(asked, false);
});

test('hub#363: the elevated attempt is sent ONCE — a second refusal is reported, not re-elevated', async () => {
  // The grant is spent at the gate BEFORE the command runs, so the token is gone whatever happens
  // next. Asking again would mint a second approval for an action that may well have already
  // happened, and looping would keep the manager tapping forever.
  const { fetchImpl, calls } = scriptedFetch([REFUSED, REFUSED]);
  let asks = 0;
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async () => {
      asks += 1;
      return `tok-${asks}`;
    },
  });

  await assert.rejects(
    () => t.command('till.sale.void', { sale_id: 's1' }),
    (e: unknown) => (e as ErploraError).code === 'requires_elevation',
  );
  assert.equal(asks, 1, 'one refusal, one dialog');
  assert.equal(calls.length, 2, 'the elevated attempt is not retried');
});

test('hub#363: a network failure on the elevated attempt is reported, never resent', async () => {
  // The worst possible resend: the request may have arrived, spent the approval and voided the
  // ticket, and only the ANSWER was lost. Sending it again would either void a second one or tell
  // the cashier to fetch the manager for something that already happened.
  const { fetchImpl, calls } = scriptedFetch([REFUSED, new Error('network down')]);
  let asks = 0;
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async () => {
      asks += 1;
      return 'tok-abc';
    },
  });

  await assert.rejects(() => t.command('till.sale.void', { sale_id: 's1' }), /network down/);
  assert.equal(asks, 1);
  assert.equal(calls.length, 2);
});

test('hub#363: a double tap on the same action opens ONE dialog and spends ONE approval', async () => {
  // Two clicks on «void» fire two commands, both refused. Without this, the manager is asked twice
  // for the same thing: one approval is spent and the other is left minted and spendable — a
  // credential lying around for whatever the cashier tries next inside the window.
  const { fetchImpl, calls } = scriptedFetch([REFUSED, REFUSED, WENT_THROUGH]);
  let asks = 0;
  let release: (token: string) => void = () => {};
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async () => {
      asks += 1;
      // The manager takes a moment to walk over: the dialog is open while the second tap lands.
      return new Promise<string>((resolve) => {
        release = resolve;
      });
    },
  });

  const first = t.command('till.sale.void', { sale_id: 's1' });
  const second = t.command('till.sale.void', { sale_id: 's1' });
  // Let both refusals come back before the manager taps.
  await new Promise((r) => setTimeout(r, 0));
  release('tok-abc');

  assert.deepEqual(await first, { voided: true });
  assert.deepEqual(await second, { voided: true }, 'both callers get the one result');
  assert.equal(asks, 1, 'one dialog for one action');
  assert.equal(calls.length, 3, 'two refusals and a single elevated send');
  assert.equal(calls[2].headers['X-Elevation-Token'], 'tok-abc');
});

test('hub#363: two DIFFERENT actions each get their own approval', async () => {
  // The coalescing above is keyed on the action, not on "an elevation is happening". Voiding table
  // 4 must never be authorised by the approval the manager gave for table 11.
  const { fetchImpl, calls } = scriptedFetch([REFUSED, REFUSED, WENT_THROUGH, WENT_THROUGH]);
  const seen: string[] = [];
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async (ask) => {
      seen.push(JSON.stringify(ask.payload));
      return `tok-${seen.length}`;
    },
  });

  await Promise.all([
    t.command('till.sale.void', { sale_id: 's1' }),
    t.command('till.sale.void', { sale_id: 's2' }),
  ]);
  assert.equal(seen.length, 2);
  assert.deepEqual(new Set(seen), new Set(['{"sale_id":"s1"}', '{"sale_id":"s2"}']));
  const tokens = calls.slice(2).map((c) => c.headers['X-Elevation-Token']);
  assert.deepEqual(new Set(tokens), new Set(['tok-1', 'tok-2']));
});

test('hub#363: a second attempt after the dialog closed asks again (the flow is not cached)', async () => {
  // Single-flight, not memoised: the cashier who cancels and taps again must get a dialog, not the
  // stale refusal of the one they closed.
  const { fetchImpl } = scriptedFetch([REFUSED, WENT_THROUGH, REFUSED, WENT_THROUGH]);
  let asks = 0;
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async () => {
      asks += 1;
      return `tok-${asks}`;
    },
  });
  await t.command('till.sale.void', { sale_id: 's1' });
  await t.command('till.sale.void', { sale_id: 's1' });
  assert.equal(asks, 2);
});

test('hub#363: without an approver configured the refusal passes through untouched', async () => {
  // A shell that never wires the dialog (a test harness, a headless host) must keep behaving
  // exactly as it did before hub#363 — never hang waiting for a dialog that does not exist.
  const { fetchImpl, calls } = scriptedFetch([REFUSED]);
  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('till.sale.void'),
    (e: unknown) => (e as ErploraError).code === 'requires_elevation',
  );
  assert.equal(calls.length, 1);
});

test('hub#363: the ask can mint an approval, and the endpoint + header are the SDK\'s to know', async () => {
  // The shell owns the pixels; the wire is the SDK's. `POST /api/elevation/approve` and
  // `X-Elevation-Token` are published contract of the runtime (hub#361) — a screen that spelled
  // them itself would be a second copy of the contract, free to drift.
  const approved = {
    ok: true,
    data: {
      token: 'tok-xyz',
      permission: 'till.void_sale',
      approved_by: 'u-sofia',
      approver_name: 'Sofía',
      expires_in_seconds: 120,
    },
  };
  const { fetchImpl, calls } = scriptedFetch([REFUSED, approved, WENT_THROUGH]);
  const t = new HttpWsTransport({
    fetchImpl,
    headers: () => ({ 'X-Hub-Id': 'h1' }),
    elevationApprover: async (ask) => (await ask.approve('Sofía', '8317')).token,
  });

  assert.deepEqual(await t.command('till.sale.void', { sale_id: 's1' }), { voided: true });
  assert.equal(calls[1].url, '/api/elevation/approve');
  assert.deepEqual(calls[1].body, {
    approver: 'Sofía',
    pin: '8317',
    command: 'till.sale.void',
    payload: { sale_id: 's1' },
  });
  assert.equal(calls[1].headers['X-Hub-Id'], 'h1', 'the cashier is authenticated as on any call');
  assert.equal(calls[2].headers['X-Elevation-Token'], 'tok-xyz');
});

test('hub#658: a BADGE mints the same approval, and it travels as a badge — not as a name+PIN', async () => {
  // The market decision of hub#658: swiping the manager's card IS the approval. It is its own door
  // on the ask (`approveWithBadge`) and not an overload of `approve`, because a badge resolves the
  // whole person — there is no name to pass. What must NOT change is the wire on the way back: the
  // same endpoint, the same `X-Elevation-Token` on the retry, the same shape of answer.
  const approved = {
    ok: true,
    data: {
      token: 'tok-badge',
      permission: 'till.void_sale',
      approved_by: 'u-sofia',
      approver_name: 'Sofía',
      expires_in_seconds: 120,
    },
  };
  const { fetchImpl, calls } = scriptedFetch([REFUSED, approved, WENT_THROUGH]);
  const t = new HttpWsTransport({
    fetchImpl,
    headers: () => ({ 'X-Hub-Id': 'h1' }),
    elevationApprover: async (ask) => (await ask.approveWithBadge('0009171456')).token,
  });

  assert.deepEqual(await t.command('till.sale.void', { sale_id: 's1' }), { voided: true });
  assert.equal(calls[1].url, '/api/elevation/approve');
  // No `approver`, no `pin`: sending an empty name next to a badge would make the runtime's
  // «one credential per request» branch depend on the emptiness of a string.
  assert.deepEqual(calls[1].body, {
    badge: '0009171456',
    command: 'till.sale.void',
    payload: { sale_id: 's1' },
  });
  assert.equal(calls[2].headers['X-Elevation-Token'], 'tok-badge');
});

test('hub#363: a refused PIN throws the runtime\'s stable code, so the dialog can try again', async () => {
  // The dialog stays open on a refusal — the manager mistyped, they retype. That only works if the
  // ask hands the failure back instead of tearing the whole flow down.
  const refusedPin = {
    ok: false,
    error: {
      code: 'hub.elevation.rejected',
      message: 'those details do not approve this action. Check the name and the PIN.',
    },
  };
  const approved = {
    ok: true,
    data: { token: 'tok-2', permission: 'till.void_sale', approved_by: 'u-sofia', approver_name: 'Sofía', expires_in_seconds: 120 },
  };
  const { fetchImpl, calls } = scriptedFetch([REFUSED, refusedPin, approved, WENT_THROUGH]);
  const codes: string[] = [];
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async (ask) => {
      try {
        await ask.approve('Sofía', '0000');
      } catch (e) {
        codes.push((e as ErploraError).code);
      }
      return (await ask.approve('Sofía', '8317')).token;
    },
  });

  assert.deepEqual(await t.command('till.sale.void', { sale_id: 's1' }), { voided: true });
  assert.deepEqual(codes, ['hub.elevation.rejected']);
  assert.equal(calls.length, 4);
});

test('hub#363: the code alone decides — a refusal without the permission field still opens a dialog', async () => {
  // The gate is `code === 'requires_elevation'`, and that is deliberate: `permission` is what the
  // DIALOG is told, not what the approval needs. `POST /api/elevation/approve` carries the command
  // and the payload and re-reads the permission from the registry itself, so a refusal that arrived
  // without the field is still an action a manager can approve — and gating on the field would
  // quietly turn it into one nobody can.
  const { fetchImpl, calls } = scriptedFetch([
    { ok: false, error: { code: 'requires_elevation', message: 'ask a manager' } },
    WENT_THROUGH,
  ]);
  const asks: ElevationAsk[] = [];
  const t = new HttpWsTransport({
    fetchImpl,
    elevationApprover: async (ask) => {
      asks.push(ask);
      return 'tok-abc';
    },
  });

  assert.deepEqual(await t.command('till.sale.void', { sale_id: 's1' }), { voided: true });
  assert.equal(asks.length, 1);
  assert.equal(asks[0].permission, '', 'nothing invented for a field the runtime did not send');
  assert.equal(calls[1].headers['X-Elevation-Token'], 'tok-abc');
});

// hub#1094: the fields a `422 invalid_payload` refused travel as a FIELD of the envelope
// (`crates/server` `err_response`, split at `registry::invalid_payload_fields`). The generic
// Settings screen the shell paints for ANY module marks those controls; parsing them out of the
// message is exactly what `permission` (hub#360) and `dependents` (hub#1101) already refuse to do.
test('hub#1094: the refused field names reach the caller as a field, never as prose', async () => {
  const fetchImpl = (async () => ({
    json: async () => ({
      ok: false,
      error: {
        code: 'invalid_payload',
        message: 'payload inválido para `kitchen.settings.update`: …',
        fields: ['auto_bump_delay_seconds', 'default_order_type'],
      },
    }),
  })) as unknown as typeof fetch;

  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('kitchen.settings.update', {}),
    (e: unknown) =>
      e instanceof ErploraError &&
      e.code === 'invalid_payload' &&
      JSON.stringify(e.fields) === JSON.stringify(['auto_bump_delay_seconds', 'default_order_type']),
  );
});

// hub#1094 × hub#1185: the core's typed refusals (`invalid_field`, hub#1070) name ONE field in the
// singular (`error.field` + a stable `reason`). One reader for «which fields were refused»: the
// singular folds into `fields`, so a screen that marks controls does not need two grammars.
test('hub#1094: an `invalid_field` refusal folds its single `field` into `fields`', async () => {
  const fetchImpl = (async () => ({
    json: async () => ({
      ok: false,
      error: {
        code: 'invalid_field',
        message: '`hub.users.create`: field `pin` too_short: 4 digits minimum',
        field: 'pin',
        reason: 'too_short',
      },
    }),
  })) as unknown as typeof fetch;

  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('hub.users.create', {}),
    (e: unknown) =>
      e instanceof ErploraError &&
      e.code === 'invalid_field' &&
      JSON.stringify(e.fields) === JSON.stringify(['pin']),
  );
});

test('hub#1094: a refusal that names no field leaves `fields` undefined, not an empty array', async () => {
  const fetchImpl = (async () => ({
    json: async () => ({ ok: false, error: { code: 'permission_denied', message: 'no' } }),
  })) as unknown as typeof fetch;

  const t = new HttpWsTransport({ fetchImpl });
  await assert.rejects(
    () => t.command('kitchen.settings.update', {}),
    (e: unknown) => e instanceof ErploraError && e.fields === undefined,
  );
});
