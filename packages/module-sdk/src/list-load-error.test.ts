// hub#2328 (pm#530) — a list that could not load must not read as an empty list. `ok-data-table`
// (OutfitKit ≥ 0.1.113) paints «could not load» + the reason + Retry when it gets `error`; the SDK
// is what every module feeds it from: the controller's `error`, the table labels, and whether the
// shell's table can paint that state at all (so a module drops its own banner only where it can).
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { createListController, dataTableLabels, dataTableShowsLoadError, type ListParams } from './index.ts';

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
