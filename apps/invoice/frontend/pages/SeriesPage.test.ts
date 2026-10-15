// Invoicing → Series (INVOICE-F12, F13; the old `erp-invoice-settings`): the intro, then the live
// `invoice.series.list` in a server-side DataTable — Code, Name, Type, Year, Prefix, Format (empty reads
// PREFIX-YYYY-NNNNNN), Current no., Active and Default —, this year's first, search «Search code, name…»;
// in cards under 1280 px. «+» opens «New numbering series» and «Edit» (or the row) «Edit series <code>», for
// whoever keeps the series; anyone else only looks. Every state of the screen.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountInvoice } from '../__tests__/mount-invoice';
import SeriesFormModal from '../components/SeriesFormModal.vue';
import type { SeriesOut } from '../operations';
import SeriesPage from './SeriesPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'invoice.series.list';

const series = (code: string, over: Partial<SeriesOut> = {}): SeriesOut => ({
  id: code,
  code,
  name: code,
  display_name: code,
  invoice_type: 'F1',
  year: 2026,
  prefix: code,
  format: '',
  current_number: 0,
  next_number: `${code}-2026-000001`,
  format_locked: false,
  is_active: true,
  is_default: false,
  ...over,
});

const PAGE = {
  rows: [series('FACT', { display_name: 'Invoices', current_number: 12, is_default: true }), series('TICKET', { invoice_type: 'F2', display_name: 'POS tickets', format: 'T{seq:05d}', is_active: false })],
  total: 2,
  limit: 50,
  offset: 0,
};

async function setup(options: MountOptions = {}) {
  const m = await mountInvoice(SeriesPage, { path: '/invoice/series', ...options });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="invoice-series-row"]');
  const show = (page: unknown) => m.result(OP, page);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  return { ...m, call, table, prop, rows, show, emit };
}

describe('SeriesPage', () => {
  it('follows invoice.series.list, this year’s first, with the intro of the old screen', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'year', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.find('invoice-series-intro').text()).toContain('Each series sets the prefix, the format and the counter');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Invoicing');
  });

  it('paints the nine columns of the old table, in cards under 1280 px', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['code', 'Code'],
      ['name', 'Name'],
      ['invoice_type', 'Type'],
      ['year', 'Year'],
      ['prefix', 'Prefix'],
      ['format', 'Format'],
      ['current_number', 'Current no.'],
      ['is_active', 'Active'],
      ['is_default', 'Default'],
    ]);
    // The window of the test is narrower than 1280 px: the rows come as cards. What each cell says is its
    // column's own text of the row.
    type Column = { key: string; format?: (value: unknown, row: SeriesOut) => string };
    const text = (row: SeriesOut) =>
      s.prop<Column[]>('columns').map((c) => (c.format ? c.format(row[c.key as keyof SeriesOut], row) : String(row[c.key as keyof SeriesOut])));
    expect(text(PAGE.rows[0])).toEqual(['FACT', 'Invoices', 'Invoice (F1)', '2026', 'FACT', 'PREFIX-YYYY-NNNNNN', '12', 'Yes', 'Yes']);
    expect(text(PAGE.rows[1])).toEqual(['TICKET', 'POS tickets', 'Ticket (F2)', '2026', 'TICKET', 'T{seq:05d}', '0', 'No', '—']);
    expect(s.rows()).toHaveLength(2);
    expect([s.prop('cardBreakpoint'), s.prop('searchPlaceholder')]).toEqual([1280, 'Search code, name…']);
  });

  it('«+» opens «New numbering series»; «Edit» or the row opens that series', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.find('invoice-series-add').trigger('click');
    await flush();
    expect([s.wrapper.findComponent(SeriesFormModal).props('open'), s.wrapper.findComponent(SeriesFormModal).props('series')]).toEqual([true, null]);
    s.wrapper.findComponent(SeriesFormModal).vm.$emit('update:open', false);
    await flush();
    await s.emit('action', { actionId: 'edit', row: PAGE.rows[1] });
    expect(s.wrapper.findComponent(SeriesFormModal).props('series')).toEqual(PAGE.rows[1]);
    await s.emit('rowClick', PAGE.rows[0]);
    expect(s.wrapper.findComponent(SeriesFormModal).props('series')).toEqual(PAGE.rows[0]);
  });

  it('whoever does not keep the series only looks', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect([s.prop('addable'), s.prop('actions'), s.prop('rowClickable')]).toEqual([false, [], false]);
    expect(s.wrapper.findComponent(SeriesFormModal).exists()).toBe(false);
  });

  it('empty, it says so; an error says it with Retry', async () => {
    const s = await setup();
    await s.show({ rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No series yet. Create the first one to number your invoices.');
    const failing = await setup();
    failing.call.push(errorFrame(failing.subId(OP), 'invoice.boom'));
    await flush();
    expect(failing.prop('error')).toBe('msg invoice.boom');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Código', 'Nombre', 'Tipo', 'Año', 'Prefijo', 'Formato', 'Nº actual', 'Activa', 'Predet.']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar código, nombre…');
  });
});
