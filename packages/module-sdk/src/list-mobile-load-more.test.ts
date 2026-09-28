// hub#2365 — On a phone `<ok-data-table serverSide>` has no pager: its only way forward is «Load
// more», which emits `pageChange(current + 1)` and leaves appending to the parent. Every module (and
// the shell's approvals) wires that event to `ListController.setPage`, so the controller is the ONE
// place where «Load more» must ADD the next page under the rows already shown instead of replacing
// them. Desktop keeps paging (replace); any new result set (search, filter, sort, size, context,
// reset) starts again at the first page.
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { createListController, type ListParams } from './index.ts';

type Row = { id: number; name: string };

/** A runtime that really pages `rows` by `offset`/`limit`, and remembers what it was asked. */
function fakeServer(count: number) {
  const server = {
    rows: Array.from({ length: count }, (_, i) => ({ id: i + 1, name: `row ${i + 1}` })) as Row[],
    calls: [] as ListParams[],
    fail: false,
    async queryPage<R>(_name: string, params: ListParams) {
      server.calls.push(structuredClone(params));
      if (server.fail) throw new Error('hub_unreachable');
      const offset = params.offset ?? 0;
      const limit = params.limit ?? 50;
      const rows = server.rows.slice(offset, offset + limit) as unknown as R[];
      return { rows, total: server.rows.length, limit, offset };
    },
  };
  return server;
}

/** A viewport the test can resize, with the same query `<ok-data-table>` watches (640 px). */
function setViewport(width: number) {
  const listeners = new Set<(e: { matches: boolean }) => void>();
  const lists: { media: string; matches: boolean }[] = [];
  const viewport = {
    width,
    resize(w: number) {
      viewport.width = w;
      for (const list of lists) {
        const matches = evaluate(list.media);
        if (matches !== list.matches) {
          list.matches = matches;
          for (const l of [...listeners]) l({ matches });
        }
      }
    },
  };
  const evaluate = (media: string) => {
    const max = /max-width:\s*(\d+)px/.exec(media);
    return max ? viewport.width <= Number(max[1]) : false;
  };
  (globalThis as Record<string, unknown>).matchMedia = (media: string) => {
    const list = {
      media,
      matches: evaluate(media),
      addEventListener: (_t: string, l: (e: { matches: boolean }) => void) => listeners.add(l),
      removeEventListener: (_t: string, l: (e: { matches: boolean }) => void) => listeners.delete(l),
    };
    lists.push(list);
    return list;
  };
  return { viewport, listeners };
}

afterEach(() => {
  delete (globalThis as Record<string, unknown>).matchMedia;
});

const flush = () => new Promise((r) => setTimeout(r, 0));
const ids = (rows: Row[]) => rows.map((r) => r.id);
const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i);

async function phoneList(count = 60, width = 390) {
  const env = setViewport(width);
  const server = fakeServer(count);
  const ctrl = createListController<Row>(server, 'kitchen.orders.list');
  await ctrl.load();
  return { ...env, server, ctrl };
}

test('on a phone «Load more» adds the next page under the rows already shown', async () => {
  const { server, ctrl } = await phoneList(60);
  assert.deepEqual(ids(ctrl.rows), range(1, 50));

  ctrl.setPage(1);
  await flush();

  assert.deepEqual(ids(ctrl.rows), range(1, 60), 'rows 1–50 stay, 51–60 are added below');
  assert.equal(ctrl.total, 60);
  assert.equal(ctrl.state.page, 1, 'the table counts what was served from the page it is on');
  const last = server.calls.at(-1)!;
  assert.equal(last.offset, 50, 'only the NEXT page is asked for, not everything again');
  assert.equal(last.limit, 50);
});

test('«Load more» keeps adding page after page', async () => {
  const { ctrl } = await phoneList(130);
  ctrl.setPage(1);
  await flush();
  ctrl.setPage(2);
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(1, 130));
  assert.equal(ctrl.state.page, 2);
});

test('on a desktop the pager still REPLACES the page', async () => {
  setViewport(1440);
  const server = fakeServer(60);
  const ctrl = createListController<Row>(server, 'm.list');
  await ctrl.load();
  ctrl.setPage(1);
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(51, 60));
  assert.equal(ctrl.state.page, 1);
});

test('without matchMedia (no window) the controller pages as before', async () => {
  const server = fakeServer(60);
  const ctrl = createListController<Row>(server, 'm.list');
  await ctrl.load();
  ctrl.setPage(1);
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(51, 60));
});

test('the phone edge is the table one: 640 px appends, 641 px pages', async () => {
  const at640 = await phoneList(60, 640);
  at640.ctrl.setPage(1);
  await flush();
  assert.deepEqual(ids(at640.ctrl.rows), range(1, 60), '640 px is a phone for <ok-data-table>');

  const at641 = await phoneList(60, 641);
  at641.ctrl.setPage(1);
  await flush();
  assert.deepEqual(ids(at641.ctrl.rows), range(51, 60), '641 px is a desktop pager');
});

test('a refresh after «Load more» (create, edit, Retry) reloads EVERYTHING shown, fresh', async () => {
  const { server, ctrl } = await phoneList(120);
  ctrl.setPage(1);
  await flush();
  server.rows[3] = { id: 4, name: 'renamed' };

  await ctrl.load();

  assert.deepEqual(ids(ctrl.rows), range(1, 100), 'the person still sees the 100 rows they had');
  assert.equal(ctrl.rows[3].name, 'renamed', 'and the rows of the first page are fresh too');
  assert.equal(ctrl.state.page, 1);
  const last = server.calls.at(-1)!;
  assert.equal(last.offset, 0, 'one request from the first row');
  assert.equal(last.limit, 100, 'as many rows as were shown');
});

for (const [name, change] of [
  ['search', (c: ReturnType<typeof createListController<Row>>) => c.setSearch('row')],
  ['filter', (c: ReturnType<typeof createListController<Row>>) => c.setFilter('status', 'open')],
  ['sort', (c: ReturnType<typeof createListController<Row>>) => c.setSort('name', 'desc')],
  ['page size', (c: ReturnType<typeof createListController<Row>>) => c.setPageSize(50)],
  ['context', (c: ReturnType<typeof createListController<Row>>) => c.setContext({ bom_id: 'b1' })],
  ['reset', (c: ReturnType<typeof createListController<Row>>) => c.reset()],
] as const) {
  test(`a new ${name} starts again at the first page, and a later refresh asks for one page`, async () => {
    const { server, ctrl } = await phoneList(120);
    ctrl.setPage(1);
    await flush();

    change(ctrl);
    await flush();
    assert.equal(ctrl.state.page, 0);
    assert.deepEqual(ids(ctrl.rows), range(1, 50), 'the first page only, not the accumulated rows');

    await ctrl.load();
    const last = server.calls.at(-1)!;
    assert.deepEqual([last.offset, last.limit], [0, 50], 'the accumulated window is gone');

    ctrl.setPage(1);
    await flush();
    assert.deepEqual(ids(ctrl.rows), range(1, 100), '«Load more» appends again from the new start');
  });
}

test('a jump that is not the next page replaces (e.g. back to the first page)', async () => {
  const { server, ctrl } = await phoneList(200);
  ctrl.setPage(1);
  await flush();
  ctrl.setPage(3);
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(151, 200), 'a jump shows that page alone');
  await ctrl.load();
  assert.deepEqual([server.calls.at(-1)!.offset, server.calls.at(-1)!.limit], [150, 50]);
  ctrl.setPage(0);
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(1, 50));
});

test('a double tap on «Load more» does not skip or duplicate a page', async () => {
  const { ctrl } = await phoneList(200);
  ctrl.setPage(1);
  ctrl.setPage(1); // second tap before the first answer: the table still says page 0
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(1, 100));
  assert.equal(ctrl.state.page, 1);
});

test('a «Load more» answer that arrives after a new search is dropped', async () => {
  const { server, ctrl } = await phoneList(120);
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const real = server.queryPage;
  server.queryPage = async <R,>(name: string, params: ListParams) => {
    if ((params.offset ?? 0) === 50) await gate;
    return real<R>(name, params);
  };
  ctrl.setPage(1);
  ctrl.setSearch('row');
  await flush();
  release();
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(1, 50), 'the stale page is not glued under the new result');
  assert.equal(ctrl.state.page, 0);
});

test('a failed «Load more» says so, and Retry brings back what was shown', async () => {
  const { server, ctrl } = await phoneList(120);
  server.fail = true;
  ctrl.setPage(1);
  await flush();
  assert.notEqual(ctrl.error, '', 'the failure is visible');
  assert.equal(ctrl.state.page, 0, 'the page it could not add is not counted as served');

  server.fail = false;
  await ctrl.load();
  assert.equal(ctrl.error, '');
  assert.deepEqual(ids(ctrl.rows), range(1, 50));
  ctrl.setPage(1);
  await flush();
  assert.deepEqual(ids(ctrl.rows), range(1, 100));
});

test('turning the phone to landscape (desktop pager) shows the current page on its own', async () => {
  const { viewport, server, ctrl } = await phoneList(120);
  ctrl.setPage(1);
  await flush();
  assert.equal(ctrl.rows.length, 100);

  viewport.resize(844);
  await flush();

  assert.deepEqual(ids(ctrl.rows), range(51, 100), 'the pager says page 2: it shows page 2');
  const last = server.calls.at(-1)!;
  assert.deepEqual([last.offset, last.limit], [50, 50]);
});

test('the viewport is not watched once nothing is accumulated', async () => {
  const { listeners, ctrl } = await phoneList(120);
  ctrl.setPage(1);
  await flush();
  assert.equal(listeners.size, 1, 'while rows are accumulated a rotation must be noticed');
  ctrl.setSearch('x');
  await flush();
  assert.equal(listeners.size, 0, 'a new result set lets the viewport go (no leak per screen)');
});

test('«Load more» on a page reached with the desktop pager fills everything up to it', async () => {
  const { viewport, server } = { ...setViewport(1440), server: fakeServer(200) };
  const ctrl = createListController<Row>(server, 'm.list');
  await ctrl.load();
  ctrl.setPage(1); // desktop: page 2 alone, rows 51–100
  await flush();
  viewport.resize(390); // the tablet becomes a phone: no pager, «Showing … » counts from row 1

  ctrl.setPage(2);
  await flush();

  assert.deepEqual(ids(ctrl.rows), range(1, 150), 'no hole: rows 1–50 are brought back too');
  assert.equal(ctrl.state.page, 2);
  const last = server.calls.at(-1)!;
  assert.deepEqual([last.offset, last.limit], [0, 150]);
});
