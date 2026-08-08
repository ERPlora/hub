// Tests del SDK con transportes mock inyectables (sin red, sin Tauri).
// node:test + tsx (sin dependencias extra). Correr: pnpm -F @erplora/module-sdk test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  HttpWsTransport,
  ErploraClient,
  ErploraError,
  createClient,
  IpcBridgeTransport,
  LocalNetworkPermissionDeniedError,
  LOCAL_NETWORK_PERMISSION_DENIED,
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
