// hub#2271 — the list controller is the ONE place that turns what a person types in a money or
// quantity filter (major units: «12», «1,5») into the integer the dispatcher compares against
// (minor units / 10⁶). A screen only says «this column is money»; it never scales by hand.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildListParams, createListController, ErploraError, type ListParams } from './index.ts';

interface FakeClient {
  currencyDecimals?: number;
  calls: ListParams[];
  queryPage<R>(name: string, params: ListParams): Promise<{ rows: R[]; total: number; limit: number; offset: number }>;
}

function fakeClient(currencyDecimals?: number): FakeClient {
  const client: FakeClient = {
    calls: [],
    async queryPage<R>(_name: string, params: ListParams) {
      client.calls.push(structuredClone(params));
      return { rows: [] as R[], total: 0, limit: 50, offset: 0 };
    },
  };
  if (currencyDecimals !== undefined) client.currencyDecimals = currencyDecimals;
  return client;
}

/** What actually travels to the runtime on the last load (`f_<col>_from` …). */
function lastWire(client: FakeClient): Record<string, unknown> {
  const last = client.calls.at(-1);
  assert.ok(last, 'the controller asked the runtime for a page');
  return buildListParams(last);
}

const flush = () => new Promise((r) => setTimeout(r, 0));

test('a money range edge typed in major units travels in minor units of the hub currency', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] });
  ctrl.setFilter('total', { from: '12' });
  await flush();
  assert.equal(lastWire(client).f_total_from, 1200, '«from 12» must not match 0,12 €');
  ctrl.setFilter('total', { to: 50 });
  await flush();
  const wire = lastWire(client);
  assert.equal(wire.f_total_from, 1200, 'the other edge is kept and still scaled');
  assert.equal(wire.f_total_to, 5000, 'the panel emits a Number: scaled too');
});

test('the typed text is normalised: decimal comma, spaces and float noise', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] });
  ctrl.setFilter('total', { from: ' 12,5 ', to: '0.29' });
  await flush();
  const wire = lastWire(client);
  assert.equal(wire.f_total_from, 1250);
  assert.equal(wire.f_total_to, 29, '0.29 × 100 is 28.999…: rounded, never truncated');
});

test('the scale is the hub currency decimals, read when the page is asked for', async () => {
  const client = fakeClient(0); // JPY: the minor unit IS the yen
  const ctrl = createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] });
  ctrl.setFilter('total', { from: '12' });
  await flush();
  assert.equal(lastWire(client).f_total_from, 12);
  client.currencyDecimals = 3; // KWD, injected by the shell after the controller was built
  ctrl.setPage(0);
  await flush();
  assert.equal(lastWire(client).f_total_from, 12000);
});

test('an edge that is not a number is dropped, never sent as 0', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] });
  ctrl.setFilter('total', { from: 'abc', to: '7' });
  await flush();
  const wire = lastWire(client);
  assert.equal('f_total_from' in wire, false, 'a stray keystroke never becomes «from 0»');
  assert.equal(wire.f_total_to, 700);
});

test('the controller state keeps what the person typed (the field is not rewritten to cents)', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] });
  ctrl.setFilter('total', { from: '12' });
  await flush();
  assert.deepEqual(ctrl.state.filters.total, { from: '12' });
});

test('only the declared columns are scaled: other ranges and plain filters travel as typed', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] });
  ctrl.setFilter('total', { from: '1' });
  ctrl.setFilter('lines', { from: '3', to: '9' });
  ctrl.setFilter('status', 'paid');
  await flush();
  const wire = lastWire(client);
  assert.equal(wire.f_total_from, 100);
  assert.equal(wire.f_lines_from, '3');
  assert.equal(wire.f_lines_to, '9');
  assert.equal(wire.f_status, 'paid');
});

test('initial money filters are scaled too, and a plain value on a money column is money', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, {
    moneyFilters: ['total', 'price'],
    filters: { total: { to: '20' } },
  });
  ctrl.setFilter('price', '4,5');
  await flush();
  const wire = lastWire(client);
  assert.equal(wire.f_total_to, 2000);
  assert.equal(wire.f_price, 450);
});

test('without moneyFilters nothing changes: the list sends what it gets (screens that scale locally)', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list');
  ctrl.setFilter('total', { from: 1200 });
  await flush();
  assert.equal(lastWire(client).f_total_from, 1200);
});

test('a quantity range edge travels in the 10⁶ scale of ADR-0147, negatives included', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, { quantityFilters: ['stock'] });
  ctrl.setFilter('stock', { from: '-2', to: '1,5' });
  await flush();
  const wire = lastWire(client);
  assert.equal(wire.f_stock_from, -2_000_000);
  assert.equal(wire.f_stock_to, 1_500_000);
});

test('declaring money filters on a client that does not know the currency decimals is refused', () => {
  const client = fakeClient();
  assert.throws(
    () => createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] }),
    (e: unknown) => e instanceof ErploraError && e.code === 'list_money_filters_need_currency_decimals',
  );
  // Quantity has a fixed scale: it does not need the currency.
  assert.doesNotThrow(() => createListController(client, 'm.list', () => {}, { quantityFilters: ['stock'] }));
});

test('an empty initial filter on a money column is left out, not turned into an error', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, {
    moneyFilters: ['total'],
    filters: { total: null },
  });
  await ctrl.load();
  assert.equal(ctrl.error, '');
  assert.equal('f_total' in lastWire(client), false);
});

test('a blank edge (only spaces) is dropped, not read as 0', async () => {
  const client = fakeClient(2);
  const ctrl = createListController(client, 'm.list', () => {}, { moneyFilters: ['total'] });
  ctrl.setFilter('total', { from: '   ', to: '3' });
  await flush();
  const wire = lastWire(client);
  assert.equal('f_total_from' in wire, false, 'Number("   ") is 0: «from 0» would hide nothing but lie');
  assert.equal(wire.f_total_to, 300);
});
