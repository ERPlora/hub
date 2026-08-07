// Tests del SDK con transportes mock inyectables (sin red, sin Tauri).
// node:test + tsx (sin dependencias extra). Correr: pnpm -F @erplora/module-sdk test
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  HttpWsTransport,
  ErploraClient,
  ErploraError,
  createClient,
  BridgeClient,
  IpcBridgeTransport,
  LocalNetworkPermissionDeniedError,
  LOCAL_NETWORK_PERMISSION_DENIED,
  eurosToCents,
  centsToEuros,
  majorToMinor,
  minorToMajor,
  dataTableLabels,
} from './index.ts';

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

// ── BridgeClient: el WS presenta el token de emparejamiento como ?token= ─────
// El Bridge es fail-closed (ADR-0050 §2.7): exige el token salvo en modo dev. Un `WebSocket`
// de navegador no puede fijar cabeceras, así que la ÚNICA vía es el query param. Si el SDK no lo
// pasa, `discoverPrinters`/`print` fallan con 401 contra un Bridge real (el gap que esto cierra).

class FakeBridgeWs {
  static last: FakeBridgeWs | undefined;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  send = (d: string) => {
    this.sent.push(d);
  };
  close = () => {};
  constructor(public url: string) {
    FakeBridgeWs.last = this;
  }
}

/** Dispara open+evento para resolver el `request()` interno del BridgeClient. */
function driveBridge(event: Record<string, unknown>): void {
  const ws = FakeBridgeWs.last!;
  ws.onopen?.();
  ws.onmessage?.({ data: JSON.stringify(event) });
}

test('BridgeClient sin token abre ws://host/ws (sin query)', async () => {
  const c = new BridgeClient(undefined, {
    WebSocketImpl: FakeBridgeWs as unknown as typeof WebSocket,
  });
  const p = c.discoverPrinters();
  assert.equal(FakeBridgeWs.last!.url, 'ws://localhost:12321/ws');
  driveBridge({ event: 'printers', printers: [] });
  await p;
});

test('BridgeClient con token emparejado lo presenta como ?token= (URL-encoded)', async () => {
  const c = new BridgeClient(undefined, {
    token: 'pair-42/x',
    WebSocketImpl: FakeBridgeWs as unknown as typeof WebSocket,
  });
  const p = c.discoverPrinters();
  assert.equal(FakeBridgeWs.last!.url, 'ws://localhost:12321/ws?token=pair-42%2Fx');
  driveBridge({ event: 'printers', printers: [] });
  await p;
});

test('BridgeClient acepta un getter de token (se relee tras emparejar, sin recrear el cliente)', async () => {
  let tok: string | null = null;
  const c = new BridgeClient(undefined, {
    token: () => tok,
    WebSocketImpl: FakeBridgeWs as unknown as typeof WebSocket,
  });
  // Antes de emparejar: sin query.
  let p = c.discoverPrinters();
  assert.equal(FakeBridgeWs.last!.url, 'ws://localhost:12321/ws');
  driveBridge({ event: 'printers', printers: [] });
  await p;
  // El usuario introduce el código en Ajustes → el MISMO cliente ya presenta el token.
  tok = 'later-token';
  p = c.discoverPrinters();
  assert.equal(FakeBridgeWs.last!.url, 'ws://localhost:12321/ws?token=later-token');
  driveBridge({ event: 'printers', printers: [] });
  await p;
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

test('el bridge WS también distingue: `error` con el code del permiso', async () => {
  const c = new BridgeClient(undefined, {
    WebSocketImpl: FakeBridgeWs as unknown as typeof WebSocket,
  });
  const p = c.discoverPrinters();
  driveBridge({
    event: 'error',
    code: LOCAL_NETWORK_PERMISSION_DENIED,
    message: 'the OS denies access to the local network',
  });

  await assert.rejects(p, (e: unknown) => e instanceof LocalNetworkPermissionDeniedError);
});

test('un error CUALQUIERA del bridge sigue siendo un Error normal', async () => {
  // Solo el permiso cambia de tipo: un fallo de transporte no debe mandar al usuario a los
  // ajustes del sistema a tocar un permiso que ya tiene.
  const c = new BridgeClient(undefined, {
    WebSocketImpl: FakeBridgeWs as unknown as typeof WebSocket,
  });
  const p = c.discoverPrinters();
  driveBridge({ event: 'error', code: 'peripheral_error', message: 'impresora inalcanzable' });

  await assert.rejects(p, (e: unknown) => {
    assert.ok(e instanceof Error);
    assert.ok(!(e instanceof LocalNetworkPermissionDeniedError));
    return true;
  });
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
