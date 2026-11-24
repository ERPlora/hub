// The Invoices page mounted with its live list (`setup`), and the invoices its tests show.
import { row } from './invoice-row';
import { liveTable } from './live-table';
import { mountInvoice, type MountOptions } from './mount-invoice';
import InvoicesPage from '../pages/InvoicesPage.vue';

export const OP = 'invoice.invoice.list';

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
  const list = liveTable(m, 'invoice-list-row');
  const params = () => m.params(OP);
  const show = (page: unknown) => m.result(OP, page);
  /** What the table's funnel applies (`v-model:filters`): the filters by name, as typed. */
  const filter = (values: Record<string, string>) => list.emit('update:filters', values);
  return { ...m, ...list, call, params, show, filter };
}
