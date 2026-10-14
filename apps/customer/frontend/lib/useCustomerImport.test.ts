// «Import CSV» (CUSTOMER-F08): the file is read here and sent in blocks of 50 to
// `customer.customer.import`; while it works the screen says «Importing…»; at the end, a summary with
// every skipped row and its reason, the rows to review and any block the server refused (the next
// blocks still go: a cut halfway leaves the blocks already sent created).
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { flush, json, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import { useCustomerImport } from './useCustomerImport';

async function setup() {
  let api!: ReturnType<typeof useCustomerImport>;
  const Probe = defineComponent({
    setup() {
      api = useCustomerImport();
      return () => h('div');
    },
  });
  const m = await mountCustomer(Probe);
  return { ...m, api: () => api };
}

const file = (text: string): File => new File([text], 'customers.csv', { type: 'text/csv' });

function csv(rows: number): string {
  return ['name,email', ...Array.from({ length: rows }, (_, i) => `C${i + 1},c${i + 1}@x.es`)].join('\n');
}

describe('useCustomerImport', () => {
  it('sends the rows in blocks of 50 and sums what the server created and skipped', async () => {
    const s = await setup();
    s.net.onApi((call) => {
      const rows = (sent(call).body as { rows: unknown[] }).rows;
      return json({ created: rows.length, skipped: 0, rows: rows.map((_, index) => ({ index, id: `id${index}`, errors: {}, warnings: {} })) });
    });
    await s.api().importFile(file(csv(120)));
    expect(s.net.api.map((c) => [sent(c).path, (sent(c).body as { rows: unknown[] }).rows.length])).toEqual([
      ['/api/customer/customers/import', 50],
      ['/api/customer/customers/import', 50],
      ['/api/customer/customers/import', 20],
    ]);
    expect(s.api().report.value).toEqual({ total: 120, created: 120, skipped: [], warnings: [], failed: [] });
    expect(s.api().importing.value).toBe(false);
  });

  it('names each skipped row by its line in the file, with the server\'s reasons, and the rows to review', async () => {
    const s = await setup();
    s.net.onApi(() =>
      json({
        created: 1,
        skipped: 1,
        rows: [
          { index: 0, id: null, errors: { name: 'This field is required.' }, warnings: {} },
          { index: 1, id: 'c2', errors: {}, warnings: { country: 'Country not recognised: imported without it.' } },
        ],
      }),
    );
    await s.api().importFile(file('name,country\n,ES\nLuis,Narnia\n'));
    expect(s.api().report.value).toEqual({
      total: 2,
      created: 1,
      skipped: [{ line: 2, reasons: ['This field is required.'] }],
      warnings: [{ line: 3, reasons: ['Country not recognised: imported without it.'] }],
      failed: [],
    });
  });

  it('a block the server refuses is reported with its lines and reason; the next blocks still go', async () => {
    const s = await setup();
    let calls = 0;
    s.net.onApi((call) => {
      calls++;
      if (calls === 1) return refusal(403, 'permission_denied', 'No permission');
      const rows = (sent(call).body as { rows: unknown[] }).rows;
      return json({ created: rows.length, skipped: 0, rows: rows.map((_, index) => ({ index, id: 'x', errors: {}, warnings: {} })) });
    });
    await s.api().importFile(file(csv(60)));
    expect(s.api().report.value).toMatchObject({ total: 60, created: 10, failed: [{ from: 2, to: 51, reason: 'No permission' }] });
  });

  it('says «Importing…» while it works', async () => {
    const s = await setup();
    let release!: (r: Response) => void;
    s.net.onApi(() => new Promise<Response>((r) => (release = r)));
    const done = s.api().importFile(file(csv(1)));
    await flush();
    expect(s.api().importing.value).toBe(true);
    release(json({ created: 1, skipped: 0, rows: [{ index: 0, id: 'a', errors: {}, warnings: {} }] }));
    await done;
    expect(s.api().importing.value).toBe(false);
  });

  it('reads a CSV that Excel saved on Windows (Windows-1252): accents and Spanish headers intact', async () => {
    const s = await setup();
    s.net.onApi(() => json({ created: 1, skipped: 0, rows: [{ index: 0, id: 'a', errors: {}, warnings: {} }] }));
    // «Nombre;Teléfono;País\nGarcía;600111222;España» in Windows-1252: é = 0xE9, í = 0xED, ñ = 0xF1.
    const bytes = new Uint8Array([
      ...'Nombre;Tel'.split('').map((c) => c.charCodeAt(0)), 0xe9, ...'fono;Pa'.split('').map((c) => c.charCodeAt(0)), 0xed, 0x73, 0x0a,
      ...'Garc'.split('').map((c) => c.charCodeAt(0)), 0xed, 0x61, ...';600111222;Espa'.split('').map((c) => c.charCodeAt(0)), 0xf1, 0x61, 0x0a,
    ]);
    await s.api().importFile(new File([bytes], 'excel.csv', { type: 'text/csv' }));
    expect(sent(s.net.api[0]).body).toEqual({ rows: [{ name: 'García', phone: '600111222', country: 'ES' }] });
  });

  it('reads UTF-8 (with or without its byte-order mark) as UTF-8', async () => {
    const s = await setup();
    s.net.onApi(() => json({ created: 1, skipped: 0, rows: [{ index: 0, id: 'a', errors: {}, warnings: {} }] }));
    await s.api().importFile(new File(['﻿Nombre;Teléfono\nGarcía;600111222\n'], 'utf8.csv'));
    expect(sent(s.net.api[0]).body).toEqual({ rows: [{ name: 'García', phone: '600111222' }] });
  });

  it('a file with no customers sends nothing and says so', async () => {
    const s = await setup();
    await s.api().importFile(file('foo,bar\n1,2\n'));
    expect(s.net.api).toHaveLength(0);
    expect(s.api().problem.value).toBe('noRows');
    expect(s.api().report.value).toBeNull();
  });

  it('«Close» drops the report; a new import replaces it', async () => {
    const s = await setup();
    s.net.onApi(() => json({ created: 1, skipped: 0, rows: [{ index: 0, id: 'a', errors: {}, warnings: {} }] }));
    await s.api().importFile(file(csv(1)));
    s.api().dismiss();
    expect(s.api().report.value).toBeNull();
    expect(s.api().problem.value).toBeNull();
  });
});
