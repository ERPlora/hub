// The Invoice page mounted with its live invoice (`setup`), and the invoice its tests show.
import type { InvoiceOut } from '../operations';
import InvoiceDetailPage from '../pages/InvoiceDetailPage.vue';
import { plain } from '../lib/format';
import { row } from './invoice-row';
import { mountInvoice, type MountOptions } from './mount-invoice';

export const OP = 'invoice.invoice.get';

export const INVOICE: InvoiceOut = {
  ...row('FACT-2026-000001'),
  id: 'i1',
  series_id: 's1',
  sequence: 1,
  operation_date: '2026-10-13',
  issuer_name: 'Peluquería Ana SL',
  issuer_tax_id: 'B12345674',
  issuer_vat_number: 'B12345674',
  issuer_address: 'Calle Mayor 1',
  issuer_country: 'ES',
  customer_id: null,
  customer_address: 'Calle Luna 3',
  customer_country: '',
  customer_id_type: '',
  description: '',
  notes: 'Thanks',
  withholding_rate: null,
  withholding_amount: 0,
  payable_amount: 1210,
  tax_breakdown: [{ tax: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', rate: '21.00', surcharge_rate: '0.00', base: 1000, quota: 210, surcharge_quota: 0 }],
  rectification_kind: '',
  sale_id: null,
  sale_number: '',
  refund_id: null,
  rectifies: null,
  substitutes: null,
  substituted_by: null,
  rectifications: [],
  remaining: 1210,
  paid_at: null,
  created_by: 'ana',
  lines: [{ id: 'l1', position: 1, description: 'Course', quantity: '1.000', unit_price: '1000.00', discount_amount: 0, tax_rate: '21.00', surcharge_rate: '0.00', tax_category_key: '', base_amount: 1000, tax_amount: 210, total_amount: 1210, product_id: null }],
};

export async function setup(options: MountOptions = {}) {
  const m = await mountInvoice(InvoiceDetailPage, { props: { id: 'i1' }, path: '/invoice/invoices/i1', ...options });
  const call = await m.live();
  const show = (invoice: unknown) => m.result(OP, invoice);
  const field = (name: string) => plain(m.find(`invoice-detail-${name}`).text());
  return { ...m, call, show, field };
}
