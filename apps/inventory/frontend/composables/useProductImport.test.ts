// The product import (WORKBOOK INVENTORY-F09), step by step as the old module did it, with the server
// as the authority: (1) the file is read and each column gets its field guessed; the whole file is
// rehearsed on the server (`dry_run`, calls of at most 100 rows) before anything is created, the tax
// category being decided later; (2) on «Import», each fiscal text of the file is read by Taxes
// (`tax.alias.resolve`); texts it does not know, and rows without one, are asked for (pick / create /
// skip; what is decided for a text is learned in Taxes); (3) the rows go in calls of at most 100 with
// «Importing done/total…» and «Stop»; a SKU repeated anywhere in the file fails on the page before it
// is sent; (4) one «Import result» adds up every call.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { type ApiCall, flush, mountInventory, ok, refusal } from '../__tests__/mount-inventory';
import { useProductImport } from './useProductImport';

type Row = { line: number; sku?: string; name?: string; tax_category_key?: string; price?: string };

/** What `bulk_create` answers: a rehearsal says «ready», a real call «created»; SKU «OLD» exists. */
function bulk(call: ApiCall) {
  const input = JSON.parse(String(call.init.body)) as { rows: Row[]; dry_run?: boolean };
  const rows = input.rows.map((row) => {
    if (row.sku === 'OLD') return { line: row.line, key: row.sku, status: 'skipped', id: null, reason: '' };
    if (!row.tax_category_key) return { line: row.line, key: row.sku ?? '', status: 'failed', id: null, reason: 'The tax category is missing' };
    if (row.price === 'x') return { line: row.line, key: row.sku ?? '', status: 'failed', id: null, reason: 'Price is not a number' };
    return { line: row.line, key: row.sku ?? '', status: input.dry_run ? 'ready' : 'created', id: null, reason: '' };
  });
  const count = (status: string) => rows.filter((row) => row.status === status).length;
  return ok({ dry_run: !!input.dry_run, total: rows.length, ready: count('ready'), created: count('created'), skipped: count('skipped'), failed: count('failed'), rows });
}

async function setup(answers: Record<string, (call: ApiCall) => Response | Promise<Response>> = {}) {
  let api: ReturnType<typeof useProductImport> | undefined;
  const Probe = defineComponent({
    setup() {
      api = useProductImport();
      return () => h('div');
    },
  });
  const m = await mountInventory(Probe);
  m.net.onApi((call) => {
    const path = call.url.split('?')[0];
    if (answers[path]) return answers[path](call);
    if (path === '/api/inventory/products/bulk_create') return bulk(call);
    if (path === '/api/tax/categories') return ok({ rows: [{ key: 'product.generic' }], total: 1, limit: 1, offset: 0 });
    if (path === '/api/tax/aliases/resolve') {
      const text = new URL(call.url, 'http://a.localhost').searchParams.get('text') ?? '';
      return ok({ text, tax_category_key: text === 'IVA 21' ? 'product.generic' : null, matched_by: text === 'IVA 21' ? 'alias' : null });
    }
    return ok({});
  });
  /** The bodies of the POSTs to `path` (a GET to the same path is a query). */
  const bodies = (path: string) => m.calls(path).filter((call) => call.init.method === 'POST').map((call) => JSON.parse(String(call.init.body)));
  return { ...m, api: () => api!, bodies };
}

const FILE = ['Nombre;Código;Precio;IVA', 'Coffee;CAF-1;2,20;IVA 21', 'Tea;TEA-1;x;IVA 21', 'Old;OLD;1;IVA 21', 'Wine;WIN-1;9;Vino', 'Water;WAT-1;1;'].join('\n');

describe('useProductImport: the preview', () => {
  it('reads the file, guesses the columns and rehearses the whole file on the server, nothing created', async () => {
    const s = await setup();
    await s.api().start(FILE);
    await flush();
    const i = s.api();
    expect(i.phase.value).toBe('preview');
    expect(i.table.value?.headers).toEqual(['Nombre', 'Código', 'Precio', 'IVA']);
    expect(i.mapping.value).toEqual(['name', 'sku', 'price', 'tax_category_key']);
    expect(i.requiredMapped.value).toBe(true);
    const [rehearsal] = s.bodies('/api/inventory/products/bulk_create');
    expect(rehearsal.dry_run).toBe(true);
    // The tax category is decided later: the rehearsal checks the rest with a category Taxes has.
    expect(rehearsal.rows[0]).toEqual({ line: 2, name: 'Coffee', sku: 'CAF-1', price: '2,20', tax_category_key: 'product.generic' });
    expect(i.rehearsal.value).toMatchObject({ status: 'ready', report: { ready: 3, skipped: 1 } });
    expect(i.rehearsal.value.report?.failed).toEqual([{ line: 3, key: 'TEA-1', reason: 'Price is not a number' }]);
  });

  it('a column changed by hand rehearses again; without Name and SKU it cannot import', async () => {
    const s = await setup();
    await s.api().start(FILE);
    await flush();
    s.api().setMapping(1, '');
    await flush();
    expect(s.api().requiredMapped.value).toBe(false);
    s.api().setMapping(0, 'sku');
    await flush();
    expect(s.api().mapping.value).toEqual(['sku', '', 'price', 'tax_category_key']);
  });

  it('a SKU repeated in the file fails on the page, even across calls of 100 rows', async () => {
    const s = await setup();
    const rows = Array.from({ length: 120 }, (_, n) => `P ${n};SKU-${n};1;IVA 21`);
    rows.push('Again;SKU-3;1;IVA 21');
    await s.api().start(['Nombre;SKU;Precio;IVA', ...rows].join('\n'));
    await flush();
    const calls = s.bodies('/api/inventory/products/bulk_create');
    expect(calls.map((body) => body.rows.length)).toEqual([100, 20]);
    expect(s.api().rehearsal.value.report?.failed).toEqual([{ line: 122, key: 'SKU-3', reason: 'SKU repeated in the file' }]);
  });

  it('a file without rows says so; Cancel leaves no trace', async () => {
    const s = await setup();
    await s.api().start('Nombre;SKU\n');
    expect([s.api().phase.value, s.api().error.value]).toEqual(['idle', 'The file has no rows to import.']);
    await s.api().start(FILE);
    s.api().cancel();
    expect([s.api().phase.value, s.api().table.value]).toEqual(['idle', null]);
  });
});

describe('useProductImport: the tax categories of the file', () => {
  it('asks for the texts Taxes does not know and for rows without one; skip leaves those rows without', async () => {
    const s = await setup();
    await s.api().start(FILE);
    await flush();
    await s.api().confirm();
    await flush();
    expect(s.calls('/api/tax/aliases/resolve').map((call) => s.query(call).text)).toEqual(['IVA 21', 'Vino']);
    expect(s.api().phase.value).toBe('tax');
    expect(s.api().unresolved.value.map((u) => u.text)).toEqual(['Vino', '']);
    s.api().setChoice('Vino', { mode: 'pick', key: 'product.generic' });
    s.api().setChoice('', { mode: 'skip' });
    await s.api().confirmTax();
    await flush();
    expect(s.bodies('/api/tax/aliases')).toEqual([{ alias: 'Vino', tax_category_key: 'product.generic' }]);
    const real = s.bodies('/api/inventory/products/bulk_create').filter((body) => !body.dry_run);
    expect(real).toHaveLength(1);
    expect(real[0].rows.map((row: Row) => [row.sku, row.tax_category_key])).toEqual([
      ['CAF-1', 'product.generic'],
      ['TEA-1', 'product.generic'],
      ['OLD', 'product.generic'],
      ['WIN-1', 'product.generic'],
      ['WAT-1', ''],
    ]);
    expect(s.api().phase.value).toBe('done');
    expect(s.api().report.value).toMatchObject({ total: 5, created: 2, skipped: 1 });
    expect(s.api().report.value?.failed.map((row) => row.reason)).toEqual(['Price is not a number', 'The tax category is missing']);
  });

  it('«Create» makes the category in Taxes and learns the text', async () => {
    const s = await setup();
    await s.api().start(FILE);
    await flush();
    await s.api().confirm();
    await flush();
    s.api().setChoice('Vino', { mode: 'create', newKey: 'drinks.wine', newName: 'Wine' });
    s.api().setChoice('', { mode: 'pick', key: 'product.generic' });
    await s.api().confirmTax();
    await flush();
    expect(s.bodies('/api/tax/categories')).toEqual([{ key: 'drinks.wine', name: 'Wine' }]);
    expect(s.bodies('/api/tax/aliases')).toEqual([{ alias: 'Vino', tax_category_key: 'drinks.wine' }]);
  });

  it('what Taxes cannot save is said in the report, and its rows fail with that reason', async () => {
    const s = await setup({ '/api/tax/aliases': () => refusal(422, 'invalid_field', 'This text is already learned.') });
    await s.api().start(FILE);
    await flush();
    await s.api().confirm();
    await flush();
    s.api().setChoice('Vino', { mode: 'pick', key: 'product.generic' });
    s.api().setChoice('', { mode: 'skip' });
    await s.api().confirmTax();
    await flush();
    const report = s.api().report.value!;
    expect(report.notes).toEqual(['Taxes could not save «Vino»: This text is already learned.']);
    expect(report.failed).toContainEqual({ line: 5, key: 'WIN-1', reason: 'Taxes could not save «Vino»: This text is already learned.' });
  });

  it('when every text is known it imports at once', async () => {
    const s = await setup();
    await s.api().start(['Nombre;SKU;IVA', 'Coffee;CAF-1;IVA 21'].join('\n'));
    await flush();
    await s.api().confirm();
    await flush();
    expect(s.api().phase.value).toBe('done');
    expect(s.api().report.value).toMatchObject({ total: 1, created: 1 });
  });
});

describe('useProductImport: one run at a time', () => {
  it('a second «Confirm & import» while the first runs is ignored: the file is imported once', async () => {
    const s = await setup();
    await s.api().start(FILE);
    await flush();
    await s.api().confirm();
    await flush();
    s.api().setChoice('Vino', { mode: 'pick', key: 'product.generic' });
    s.api().setChoice('', { mode: 'skip' });
    const first = s.api().confirmTax();
    expect(s.api().busy.value).toBe(true);
    const second = s.api().confirmTax();
    await Promise.all([first, second]);
    await flush();
    expect(s.bodies('/api/tax/aliases')).toHaveLength(1);
    expect(s.bodies('/api/inventory/products/bulk_create').filter((body) => !body.dry_run)).toHaveLength(1);
    expect(s.api().busy.value).toBe(false);
  });

  it('a second «Import» while the first resolves the texts is ignored', async () => {
    const s = await setup();
    await s.api().start(FILE);
    await flush();
    await Promise.all([s.api().confirm(), s.api().confirm()]);
    await flush();
    expect(s.calls('/api/tax/aliases/resolve')).toHaveLength(2);
  });

  it('a rehearsal superseded by a new column stops sending its calls', async () => {
    const pending: Array<() => void> = [];
    const s = await setup({
      '/api/inventory/products/bulk_create': (call) =>
        new Promise<Response>((resolve) => {
          pending.push(() => resolve(bulk(call)));
        }),
    });
    const rows = Array.from({ length: 250 }, (_, n) => `P ${n};SKU-${n};1;product.generic`);
    const started = s.api().start(['Nombre;SKU;Precio;IVA', ...rows].join('\n'));
    await flush();
    expect(s.bodies('/api/inventory/products/bulk_create')).toHaveLength(1);
    s.api().setMapping(2, '');
    await flush();
    pending.shift()!(); // the first rehearsal's first call answers after it was superseded
    await flush();
    while (pending.length) {
      pending.shift()!();
      await flush();
    }
    await started;
    await flush();
    const calls = s.bodies('/api/inventory/products/bulk_create');
    // The new rehearsal's 3 calls, plus only the 1 the old one had sent: it never sent its 2nd.
    expect(calls).toHaveLength(4);
    expect(calls.filter((body) => body.rows[0].price !== undefined)).toHaveLength(1);
    expect(s.api().rehearsal.value).toMatchObject({ status: 'ready', report: { ready: 250 } });
  });
});

describe('useProductImport: running', () => {
  it('goes in calls of at most 100 rows with its progress; «Stop» leaves the rest untouched and says so', async () => {
    let release: (() => void) | undefined;
    const s = await setup({
      '/api/inventory/products/bulk_create': (call) => {
        const body = JSON.parse(String(call.init.body)) as { dry_run?: boolean };
        if (body.dry_run) return bulk(call);
        return new Promise<Response>((resolve) => {
          release = () => resolve(bulk(call));
        });
      },
    });
    const rows = Array.from({ length: 250 }, (_, n) => `P ${n};SKU-${n};IVA 21`);
    await s.api().start(['Nombre;SKU;IVA', ...rows].join('\n'));
    await flush();
    const running = s.api().confirm();
    await flush();
    expect(s.api().progress.value).toEqual({ done: 0, total: 250 });
    release!();
    await flush();
    expect(s.api().progress.value).toEqual({ done: 100, total: 250 });
    s.api().stop();
    release!();
    await running;
    await flush();
    const real = s.bodies('/api/inventory/products/bulk_create').filter((body) => !body.dry_run);
    expect(real).toHaveLength(2);
    // «Rows» are the file's: the 50 never sent are the part «left untouched».
    expect(s.api().report.value).toMatchObject({ total: 250, created: 200, cancelled: true });
    expect(s.api().progress.value).toBeNull();
  });
});
