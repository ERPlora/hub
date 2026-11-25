// Online orders → Table QR codes (ONLINE_ORDER-F01, F02): every table in the floor plan's order, live, with its zone,
// the address its QR opens and when it was generated. «Print sheet» prints one QR per table to cut out; a row prints
// its own. «Regenerate QR» asks first, because the printed QR stops working at once; a table without a code gets
// its first one without asking, and «Generate the missing QR codes» gives one to every table still without.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { offeredRowActions, pressRowAction } from '@erplora/ui/testing/data-table';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { BYE, codeRow, errorFrame, flush, type MountOptions, mountOnlineOrder, page, VIEWER } from '../__tests__/mount-online-order';
import QrCodesPage from './QrCodesPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), print: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('../../../../base/frontend/lib/print', () => ({ printPaper: mocks.print }));
vi.mock('../composables/useQrImages', async () => {
  const { computed, toValue } = await import('vue');
  return {
    useQrImages: (urls: () => string[]) => ({
      images: computed(() => Object.fromEntries(toValue(urls).map((url) => [url, `data:image/png;base64,${url.slice(-6)}`]))),
      ready: computed(() => true),
    }),
  };
});

const OP = 'online_order.qr_code.list';
const REGENERATE = '/api/online_order/qr_codes/regenerate';
const FOUR = codeRow({ number: '4' });
const TEN = codeRow({ number: '10', zone_name: null, table: '10' });
const BARE = codeRow({ number: '12', code: null });

beforeEach(() => {
  mocks.confirm.mockReset();
  mocks.print.mockReset();
});

async function setup(options: MountOptions = {}) {
  const m = await mountOnlineOrder(QrCodesPage, options);
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const cells = (i: number) =>
    m.wrapper.findAll('[data-testid="online-order-qr-row"]')[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const show = (rows: ReturnType<typeof codeRow>[]) => m.result(OP, page(rows, rows.length, 100, 0));
  const printButton = () => m.find('online-order-qr-print');
  const printable = () => !(printButton().element as HTMLElement & { disabled: boolean }).disabled;
  const printed = () => {
    const [paper, options] = mocks.print.mock.calls.at(-1) as [HTMLElement, { title: string }];
    const cards = [...paper.querySelectorAll('[data-testid="online-order-qr-sheet-card"]')];
    return { title: options.title, tables: cards.map((card) => card.querySelectorAll('p')[1].textContent?.trim()) };
  };
  return { ...m, table, prop, cells, show, printButton, printable, printed };
}

describe('QrCodesPage: the list', () => {
  it('follows every table in the floor plan’s order with Table, Zone, Address and Generated', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ limit: 100, offset: 0 }]);
    expect(s.prop('loading')).toBe(true);
    await s.show([FOUR, TEN, BARE]);
    expect(s.prop('loading')).toBe(false);
    expect(s.prop<{ key: string; label: string }[]>('columns').map((c) => [c.key, c.label])).toEqual([
      ['number', 'Table'],
      ['zone_name', 'Zone'],
      ['url', 'Address'],
      ['issued_at', 'Generated'],
    ]);
    expect(s.cells(0).slice(0, 3)).toEqual(['4', 'Terrace', FOUR.url]);
    expect(s.cells(0)[3]).toMatch(/2026/);
    expect(s.cells(1).slice(0, 2)).toEqual(['10', 'No zone']);
    expect(s.cells(2).slice(0, 4)).toEqual(['12', 'Terrace', 'No QR yet', 'No QR yet']);
  });

  it('without tables says so and sends to Tables', async () => {
    const s = await setup();
    await s.show([]);
    const empty = s.wrapper.findComponent(EmptyState);
    expect([empty.props('heading'), empty.props('message')]).toEqual([
      'No tables yet',
      'Add the tables of your room in Tables: each one gets its own QR.',
    ]);
    await s.find('online-order-qr-to-tables').trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/table/tables');
    expect(s.printable()).toBe(false);
  });

  it('whoever may not add tables gets no way to Tables', async () => {
    const s = await setup({ session: VIEWER });
    await s.show([]);
    expect(s.find('online-order-qr-empty').exists()).toBe(true);
    expect(s.find('online-order-qr-to-tables').exists()).toBe(false);
  });

  it('says it is reconnecting while the stream recovers, and keeps what it painted', async () => {
    const s = await setup();
    await s.show([FOUR]);
    s.net.lastStream().push(BYE);
    await flush();
    expect(s.find('online-order-qr-reconnecting').text()).toBe('Reconnecting…');
    expect(s.cells(0)[0]).toBe('4');
  });

  it('a list that does not load says why and retries', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'base.unavailable'));
    await flush();
    expect(s.prop('error')).toBe('msg base.unavailable');
    const streams = s.net.streams.length;
    s.table().vm.$emit('retry');
    await flush();
    await s.reopen();
    expect(s.net.streams.length).toBeGreaterThan(streams);
    expect(s.params(OP)).toEqual([{ limit: 100, offset: 0 }]);
    await s.show([FOUR]);
    expect(s.prop('error')).toBeUndefined();
    expect(s.cells(0)[0]).toBe('4');
  });
});

describe('QrCodesPage: printing', () => {
  it('«Print sheet» waits for the list and prints one card per table with a QR, in order', async () => {
    const s = await setup();
    expect(s.printable()).toBe(false);
    await s.show([FOUR, BARE, TEN]);
    expect(s.printable()).toBe(true);
    await s.printButton().trigger('click');
    await flush();
    expect(s.printed()).toEqual({ title: 'QR codes of the tables', tables: ['Table 4', 'Table 10'] });
  });

  it('«Print sheet» stays off until every window of a long list has come', async () => {
    const s = await setup();
    await s.result(OP, page([FOUR], 150, 100, 0));
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { limit: 100, offset: 0 },
      { limit: 100, offset: 100 },
    ]);
    await s.result(OP, page([FOUR], 150, 100, 0), { offset: 0 });
    expect(s.printable()).toBe(false);
    await s.result(OP, page([TEN], 150, 100, 100), { offset: 100 });
    expect(s.printable()).toBe(true);
  });

  it('«Print sheet» can print again once a print has finished', async () => {
    const s = await setup();
    await s.show([FOUR]);
    await s.printButton().trigger('click');
    await flush();
    expect(s.printable()).toBe(true);
    await s.printButton().trigger('click');
    await flush();
    expect(mocks.print).toHaveBeenCalledTimes(2);
  });

  it('«Print QR» of a row prints only that table', async () => {
    const s = await setup();
    await s.show([FOUR, TEN]);
    await pressRowAction(s.wrapper, 't10', 'print');
    await flush();
    expect(s.printed().tables).toEqual(['Table 10']);
  });

  it('a sheet that cannot be printed says so', async () => {
    mocks.print.mockRejectedValue(new Error('blocked'));
    const s = await setup();
    await s.show([FOUR]);
    await s.printButton().trigger('click');
    await flush();
    expect(toastError).toHaveBeenCalledWith('The sheet could not be printed.');
  });

  it('says which tables are not on the sheet', async () => {
    const s = await setup();
    await s.show([FOUR, BARE]);
    expect(s.find('online-order-qr-missing').text()).toContain('1 table has no QR yet, so it is not on the sheet.');
    await s.show([FOUR]);
    expect(s.find('online-order-qr-missing').exists()).toBe(false);
  });
});

describe('QrCodesPage: generating and regenerating', () => {
  it('offers Print and Regenerate on a table with a QR, and Generate on one without', async () => {
    const s = await setup();
    await s.show([FOUR, BARE]);
    expect(offeredRowActions(s.wrapper, 't4')).toEqual(['print', 'regenerate']);
    expect(offeredRowActions(s.wrapper, 't12')).toEqual(['generate']);
  });

  it('«Regenerate QR» asks first and, confirmed, gives the table a new code', async () => {
    mocks.confirm.mockResolvedValue(true);
    const s = await setup();
    await s.show([FOUR]);
    s.answer(200, { ...FOUR, code: 'new' });
    await pressRowAction(s.wrapper, 't4', 'regenerate');
    await flush();
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Regenerate the QR of table 4 (Terrace)?',
      message: 'The QR printed for this table stops working at once. Print the new one and swap it on the table.',
      confirmLabel: 'Regenerate QR',
      tone: 'danger',
    });
    expect(s.sent()).toEqual([{ method: 'POST', path: REGENERATE, query: {}, body: { id: 't4' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Table 4 (Terrace) has a new QR. Print it and swap the old one.');
  });

  it('a regeneration not confirmed changes nothing', async () => {
    mocks.confirm.mockResolvedValue(false);
    const s = await setup();
    await s.show([FOUR]);
    await pressRowAction(s.wrapper, 't4', 'regenerate');
    await flush();
    expect(s.sent()).toEqual([]);
  });

  it('«Generate QR» gives a table its first code without asking', async () => {
    const s = await setup();
    await s.show([BARE]);
    s.answer(200, { ...BARE, code: 'first' });
    await pressRowAction(s.wrapper, 't12', 'generate');
    await flush();
    expect(mocks.confirm).not.toHaveBeenCalled();
    expect(s.sent()).toEqual([{ method: 'POST', path: REGENERATE, query: {}, body: { id: 't12' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Table 12 (Terrace) has its QR.');
  });

  it('a refused regeneration says why', async () => {
    mocks.confirm.mockResolvedValue(true);
    const s = await setup();
    await s.show([FOUR]);
    s.answer(404, { error: { code: 'table.not_found', message: 'That table does not exist in this business.' } });
    await pressRowAction(s.wrapper, 't4', 'regenerate');
    await flush();
    expect(toastError).toHaveBeenCalledWith('That table does not exist in this business.');
  });

  it('«Generate the missing QR codes» gives one to each table without, in order', async () => {
    const s = await setup();
    await s.show([BARE, FOUR, codeRow({ number: '14', code: null })]);
    s.answer(200, BARE);
    await s.find('online-order-qr-generate-missing').trigger('click');
    await flush();
    expect(s.sent().map((call) => call.body)).toEqual([{ id: 't12' }, { id: 't14' }]);
    expect(toastSuccess).toHaveBeenCalledWith('2 tables have their QR.');
  });

  it('stops at the first table that cannot get its code, and says why', async () => {
    const s = await setup();
    await s.show([BARE, codeRow({ number: '14', code: null })]);
    s.answer(404, { error: { code: 'table.not_found', message: 'That table does not exist in this business.' } });
    await s.find('online-order-qr-generate-missing').trigger('click');
    await flush();
    expect(s.sent()).toHaveLength(1);
    expect(toastError).toHaveBeenCalledWith('That table does not exist in this business.');
  });

  it('whoever may only see the codes prints them, and neither generates nor regenerates', async () => {
    const s = await setup({ session: VIEWER });
    await s.show([FOUR, BARE]);
    expect(offeredRowActions(s.wrapper, 't4')).toEqual(['print']);
    expect(offeredRowActions(s.wrapper, 't12')).toEqual([]);
    expect(s.find('online-order-qr-generate-missing').exists()).toBe(false);
  });
});

describe('QrCodesPage in Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show([FOUR, BARE]);
    expect(s.printButton().text()).toBe('Imprimir hoja');
    expect(s.cells(1)[2]).toBe('Sin QR todavía');
    expect(s.find('online-order-qr-missing').text()).toContain('1 mesa aún no tiene QR, así que no sale en la hoja.');
  });
});
