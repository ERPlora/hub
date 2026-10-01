// hub#2328 (pm#530) — a list that could not load must not read as an empty list. `ok-data-table`
// (OutfitKit ≥ 0.1.113) paints «could not load» + the reason + Retry when it gets `error`; the SDK
// is what every module feeds it from: the controller's `error`, the table labels, and whether the
// shell's table can paint that state at all (so a module drops its own banner only where it can).
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  createListController,
  dataTableLabels,
  dataTableShowsLoadError,
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  SERVER_UNAVAILABLE,
  type ListParams,
} from './index.ts';

type Page = { rows: unknown[]; total: number; limit: number; offset: number };

function failingClient(reason: unknown) {
  return {
    async queryPage<R>(_name: string, _params: ListParams): Promise<Page & { rows: R[] }> {
      throw reason;
    },
  };
}

/** The shell language, read where `erplora().locale` reads it. */
function withShellLocale(locale: string) {
  (globalThis as { localStorage?: unknown }).localStorage = {
    getItem: (k: string) => (k === 'erplora.locale' ? locale : null),
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

const realCustomElements = (globalThis as { customElements?: unknown }).customElements;
const realStorage = (globalThis as { localStorage?: unknown }).localStorage;
afterEach(() => {
  (globalThis as { customElements?: unknown }).customElements = realCustomElements;
  (globalThis as { localStorage?: unknown }).localStorage = realStorage;
});

function registerTable(proto: object | null) {
  (globalThis as { customElements?: unknown }).customElements = {
    get: (tag: string) => (tag === 'ok-data-table' && proto ? { prototype: proto } : undefined),
  };
}

test('the table labels carry the load-error title and the retry button in en and es', () => {
  const en = dataTableLabels('en');
  const es = dataTableLabels('es');
  for (const key of ['loadError', 'retry']) {
    assert.ok(en[key]?.trim(), `en.${key} is missing: the table would fall back to its own language`);
    assert.ok(es[key]?.trim(), `es.${key} is missing: a Spanish hub would read the English default`);
    assert.notEqual(en[key], es[key], `${key} is not translated`);
  }
});

test('every table label exists in both languages', () => {
  assert.deepEqual(Object.keys(dataTableLabels('es')).sort(), Object.keys(dataTableLabels('en')).sort());
});

test('a failure with a message keeps that message as the reason and clears the page', async () => {
  const ctrl = createListController(failingClient(new Error('hub down')), 'm.list');
  ctrl.rows = [{ id: 1 }];
  ctrl.total = 1;
  await ctrl.load();
  assert.equal(ctrl.error, 'hub down');
  assert.deepEqual(ctrl.rows, []);
  assert.equal(ctrl.total, 0);
  assert.equal(ctrl.loading, false);
});

test('a failure WITHOUT a message still sets a non-blank error in the shell language', async () => {
  // A blank `error` is «no error» for the table: it would go back to «No customers» + «0 records».
  for (const reason of [new Error(''), new Error('   '), 'boom', undefined]) {
    withShellLocale('en');
    const en = createListController(failingClient(reason), 'm.list');
    await en.load();
    withShellLocale('es');
    const es = createListController(failingClient(reason), 'm.list');
    await es.load();
    assert.ok(en.error.trim(), `en: ${String(reason)} left the error blank`);
    assert.ok(es.error.trim(), `es: ${String(reason)} left the error blank`);
    assert.notEqual(en.error, es.error, `${String(reason)}: the fallback is not localized`);
  }
});

test('retrying with load() clears the error and paints the page that now arrives', async () => {
  let fail = true;
  const client = {
    async queryPage<R>(_name: string, _params: ListParams): Promise<Page & { rows: R[] }> {
      if (fail) throw new Error('hub down');
      return { rows: [{ id: 7 }] as R[], total: 1, limit: 50, offset: 0 };
    },
  };
  let changes = 0;
  const ctrl = createListController(client, 'm.list', () => changes++);
  await ctrl.load();
  assert.equal(ctrl.error, 'hub down');
  fail = false;
  const before = changes;
  const retry = ctrl.load();
  assert.equal(ctrl.error, '', 'the error clears as soon as the retry starts');
  await retry;
  await flush();
  assert.equal(ctrl.error, '');
  assert.deepEqual(ctrl.rows, [{ id: 7 }]);
  assert.equal(ctrl.total, 1);
  assert.ok(changes > before, 'the screen is told to repaint');
});

test('dataTableShowsLoadError: true only when the registered ok-data-table has the error property', () => {
  class WithError {}
  Object.defineProperty(WithError.prototype, 'error', { get: () => '', set: () => {}, configurable: true });
  registerTable(WithError.prototype);
  assert.equal(dataTableShowsLoadError(), true);

  registerTable(class Old {}.prototype);
  assert.equal(dataTableShowsLoadError(), false, 'an older shell table would drop the reason');

  registerTable(null);
  assert.equal(dataTableShowsLoadError(), false, 'no table registered yet');

  (globalThis as { customElements?: unknown }).customElements = undefined;
  assert.equal(dataTableShowsLoadError(), false, 'no DOM at all');
});

// hub#2404 — the table paints its own heading («Couldn't load the data») above the reason, so a
// reason that opens with the same «could not be loaded» reads twice in a row. Where the table paints
// the error, an unreachable read gives only the WHY and the WHAT TO DO; where the module paints the
// reason alone (an older shell table, `dataTableShowsLoadError()` false), it keeps the full sentence.

/** The proxy's answer while the hub container is down: a 502 HTML page (as in hub#2288). */
const proxy502Fetch = (async () => ({
  ok: false,
  status: 502,
  headers: { get: (n: string) => (n.toLowerCase() === 'content-type' ? 'text/html' : null) },
  json: async () => JSON.parse('<!DOCTYPE html><html>bad gateway</html>'),
})) as unknown as typeof fetch;

function unreachableHub() {
  return new ErploraClient(new HttpWsTransport({ baseUrl: 'http://h', fetchImpl: proxy502Fetch }));
}

function registerTableWithError() {
  class WithError {}
  Object.defineProperty(WithError.prototype, 'error', { get: () => '', set: () => {}, configurable: true });
  registerTable(WithError.prototype);
}

const LANGS = [
  { locale: 'es', restatesLoad: /cargar/i, notResponding: /el hub no responde/i, action: 'Comprueba la conexión e inténtalo de nuevo' },
  { locale: 'en', restatesLoad: /load/i, notResponding: /the hub is not responding/i, action: 'Check the connection and try again' },
];

for (const lang of LANGS) {
  test(`hub#2404 (${lang.locale}): under the table's heading, an unreachable hub's reason does not repeat «could not load»`, async () => {
    withShellLocale(lang.locale);
    registerTableWithError();
    const ctrl = createListController(unreachableHub(), 'customers.list');
    await ctrl.load();
    assert.ok(lang.restatesLoad.test(dataTableLabels(lang.locale).loadError), 'control: the heading says it');
    assert.ok(!lang.restatesLoad.test(ctrl.error), `the reason repeats the heading: ${ctrl.error}`);
    assert.match(ctrl.error, lang.notResponding, 'the reason still says why');
    assert.ok(ctrl.error.includes(lang.action), `the reason still says what to do: ${ctrl.error}`);
  });

  test(`hub#2404 (${lang.locale}): with an older table the module's banner keeps the full, self-standing sentence`, async () => {
    withShellLocale(lang.locale);
    registerTable(class Old {}.prototype);
    const ctrl = createListController(unreachableHub(), 'customers.list');
    await ctrl.load();
    assert.ok(lang.restatesLoad.test(ctrl.error), `a banner without a heading must say the data did not load: ${ctrl.error}`);
    assert.ok(ctrl.error.includes(lang.action), ctrl.error);
  });
}

test('hub#2404: a reason the module or the hub DID give is never rewritten under the table', async () => {
  registerTableWithError();
  const refusal = new ErploraError('customers.forbidden', 'No tienes permiso para ver clientes');
  const ctrl = createListController(failingClient(refusal), 'customers.list');
  await ctrl.load();
  assert.equal(ctrl.error, 'No tienes permiso para ver clientes');
});

test('hub#2404: the error comes from the SHELL\'s client, another bundle — its class is not this ErploraError', async () => {
  // A module bakes its own copy of the SDK (and of ListController), but the read goes through
  // `globalThis.erplora`, the shell's client: the error it throws is an ErploraError of THAT bundle,
  // so `instanceof` is false here. Only its `code` crosses the boundary.
  class ShellErploraError extends Error {
    constructor(readonly code: string, message: string) {
      super(message);
    }
  }
  const fromShell = new ShellErploraError(
    SERVER_UNAVAILABLE,
    'No se han podido cargar los datos porque el hub no responde. Comprueba la conexión e inténtalo de nuevo.',
  );
  assert.ok(!(fromShell instanceof ErploraError), 'control: it is not this bundle\'s class');
  withShellLocale('es');
  registerTableWithError();
  const ctrl = createListController(failingClient(fromShell), 'customers.list');
  await ctrl.load();
  assert.equal(ctrl.error, 'El hub no responde. Comprueba la conexión e inténtalo de nuevo.');
});
