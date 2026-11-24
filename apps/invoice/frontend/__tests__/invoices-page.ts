// The Invoices page mounted with its live list (`setup`), and the invoices its tests show.
import { DataTable } from '@erplora/ui/components';
import type { Component } from 'vue';

import { flush, mountInvoice, type MountOptions } from './mount-invoice';
import InvoicesPage from '../pages/InvoicesPage.vue';
import type { InvoiceRowOut } from '../operations';

export const OP = 'invoice.invoice.list';

export const row = (number: string, over: Partial<InvoiceRowOut> = {}): InvoiceRowOut => ({
  id: number,
  number,
  invoice_type: 'F1',
  series_code: 'FACT',
  year: 2026,
  issue_date: '2026-10-14',
  issued_at: '2026-10-14T10:00:00Z',
  customer_name: 'Talleres Pérez SL',
  customer_tax_id: 'B12345674',
  base_amount: 1000,
  tax_amount: 210,
  total_amount: 1210,
  currency: 'EUR',
  currency_decimals: 2,
  status: 'issued',
  source_type: 'manual',
  rectifies_id: null,
  rectifies_number: '',
  substituted: false,
  can_mark_paid: true,
  can_rectify: true,
  can_substitute: false,
  ...over,
});

export const PAGE = {
  rows: [
    row('FACT-2026-000002'),
    row('TICKET-2026-000001', { invoice_type: 'F2', customer_name: '', status: 'paid', can_mark_paid: false, can_substitute: true, source_type: 'sale' }),
    row('RECT-2026-000001', { invoice_type: 'R1', total_amount: -1210, status: 'issued', can_mark_paid: false, can_rectify: false, rectifies_number: 'FACT-2026-000001' }),
  ],
  total: 3,
  limit: 50,
  offset: 0,
};
export const EMPTY = { rows: [], total: 0, limit: 50, offset: 0 };

export async function setup(options: MountOptions = {}) {
  const m = await mountInvoice(InvoicesPage, options);
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="invoice-list-row"]');
  const params = () => m.params(OP);
  const show = (page: unknown) => m.result(OP, page);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  /** What the table's funnel applies (`v-model:filters`): the filters by name, as typed. */
  const filter = (values: Record<string, string>) => emit('update:filters', values);
  return { ...m, call, table, prop, rows, params, show, emit, filter };
}
