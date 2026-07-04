// Tests del SDK con transportes mock inyectables (sin red, sin Tauri).
// node:test + tsx (sin dependencias extra). Correr: pnpm -F @erplora/module-sdk test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  HttpWsTransport,
  ErploraClient,
  ErploraError,
  createClient,
} from './index.ts';

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
