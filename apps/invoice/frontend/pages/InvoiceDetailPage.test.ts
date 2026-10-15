// The open invoice (INVOICE-F17, F18, F19, F05, F08; the old detail of `erp-invoice-list`): «Invoice
// <number>» with its status, «Print / PDF» and «Back»; the warning of a full invoice without the customer's
// tax ID; Type, Series, Issue date (and Operation date when it differs), Customer, tax ID, Address, Issuer,
// Source, Sale, the documents it rectifies or replaces or is replaced or rectified by (each opens), Paid on
// and Notes; the lines, the breakdown and the totals; «Mark as paid», «Rectify» and «Full invoice» where
// they apply and for whoever may. It follows `invoice.invoice.get` live: a payment or a rectification made
// elsewhere shows by itself.
import { AppPage } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, errorFrame, flush, type MountOptions, mountInvoice } from '../__tests__/mount-invoice';
import InvoiceLinesTable from '../components/InvoiceLinesTable.vue';
import InvoicePaper from '../components/InvoicePaper.vue';
import RectifyModal from '../components/RectifyModal.vue';
import SubstituteModal from '../components/SubstituteModal.vue';
import { plain } from '../lib/format';
import type { InvoiceOut } from '../operations';
import InvoiceDetailPage from './InvoiceDetailPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), print: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('../../../sale/frontend/lib/print', () => ({ printPaper: mocks.print }));
beforeEach(() => {
  mocks.confirm.mockReset();
  mocks.print.mockReset();
});

const OP = 'invoice.invoice.get';

const INVOICE: InvoiceOut = {
  id: 'i1',
  number: 'FACT-2026-000001',
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
  status: 'issued',
  source_type: 'manual',
  rectifies_id: null,
  rectifies_number: '',
  substituted: false,
  can_mark_paid: true,
  can_rectify: true,
  can_substitute: false,
  series_id: 's1',
  sequence: 1,
  operation_date: '2026-10-13',
  issuer_name: 'Peluquería Ana SL',
  issuer_tax_id: 'B12345674',
  issuer_address: 'Calle Mayor 1',
  issuer_country: 'ES',
  customer_id: null,
  customer_address: 'Calle Luna 3',
  customer_country: '',
  customer_id_type: '',
  description: '',
  notes: 'Thanks',
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

async function setup(options: MountOptions = {}) {
  const m = await mountInvoice(InvoiceDetailPage, { props: { id: 'i1' }, path: '/invoice/invoices/i1', ...options });
  const call = await m.live();
  const show = (invoice: unknown) => m.result(OP, invoice);
  const field = (name: string) => plain(m.find(`invoice-detail-${name}`).text());
  return { ...m, call, show, field };
}

describe('InvoiceDetailPage: what it shows', () => {
  it('follows invoice.invoice.get for its id, with a spinner until it arrives', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ invoice_id: 'i1' }]);
    expect(s.find('invoice-detail-loading').exists()).toBe(true);
    await s.show(INVOICE);
    expect(s.find('invoice-detail-loading').exists()).toBe(false);
  });

  it('is «Invoice <number>» with its status, Print and Back, under Invoicing with a way back to the list', async () => {
    const s = await setup();
    await s.show(INVOICE);
    expect(s.field('title')).toBe('Invoice FACT-2026-000001');
    expect(s.field('status')).toBe('Issued');
    expect(s.field('print')).toBe('Print / PDF');
    expect(s.wrapper.findComponent(AppPage).props('backHref')).toBe('/invoice/invoices');
  });

  it('paints the fields of the old detail', async () => {
    const s = await setup();
    await s.show(INVOICE);
    expect(s.field('type')).toBe('Invoice (F1)');
    expect(s.field('series')).toBe('FACT');
    expect(s.field('issue-date')).toBe('10/14/2026');
    expect(s.field('operation-date')).toBe('10/13/2026');
    expect(s.field('customer')).toBe('Talleres Pérez SL');
    expect(s.field('customer-tax-id')).toBe('B12345674');
    expect(s.field('address')).toBe('Calle Luna 3');
    expect(s.field('issuer')).toBe('Peluquería Ana SL (B12345674)');
    expect(s.field('source')).toBe('Manual');
    expect(s.field('notes')).toBe('Thanks');
    expect(s.find('invoice-detail-paid-at').exists()).toBe(false);
    expect(s.wrapper.findComponent(InvoiceLinesTable).props('lines')).toEqual(INVOICE.lines);
    expect(s.find('invoice-missing-tax-id').exists()).toBe(false);
  });

  it('warns of a full invoice without the customer’s tax ID', async () => {
    const s = await setup();
    await s.show({ ...INVOICE, customer_tax_id: '' });
    expect(s.find('invoice-missing-tax-id').text()).toContain('the ticket printer cannot print it as a full invoice');
  });

  it('a rectifying invoice names what it rectifies (a link) and its reason', async () => {
    const s = await setup();
    await s.show({
      ...INVOICE,
      invoice_type: 'R1',
      source_type: 'refund',
      description: 'Broken',
      notes: '',
      rectifies: { id: 'o1', number: 'FACT-2025-000009', invoice_type: 'F1', status: 'cancelled', issue_date: '2025-12-01', total_amount: 1210 },
      sale_number: '20261014-0003',
      can_mark_paid: false,
      can_rectify: false,
    });
    expect(s.field('notes')).toBe('Rectifies invoice FACT-2025-000009. Reason: Broken');
    expect(s.field('sale')).toBe('20261014-0003');
    const push = vi.spyOn(s.router, 'push');
    await click(s.find('invoice-detail-rectifies-link').element);
    expect(push).toHaveBeenCalledWith('/invoice/invoices/o1');
    expect(s.find('invoice-detail-mark-paid').exists()).toBe(false);
    expect(s.find('invoice-detail-rectify').exists()).toBe(false);
  });

  it('a replaced ticket says by which invoice, and that one by which ticket', async () => {
    const s = await setup();
    await s.show({ ...INVOICE, invoice_type: 'F2', substituted: true, substituted_by: { id: 'f3', number: 'FACT-2026-000002', invoice_type: 'F3', status: 'paid', issue_date: '2026-10-14', total_amount: 1210 } });
    expect(s.field('substituted-by')).toBe('FACT-2026-000002');
  });

  it('a paid invoice says when', async () => {
    const s = await setup();
    await s.show({ ...INVOICE, status: 'paid', paid_at: '2026-10-14T10:00:00Z', can_mark_paid: false });
    expect(s.field('paid-at')).not.toBe('');
    expect(s.find('invoice-detail-mark-paid').exists()).toBe(false);
  });
});

describe('InvoiceDetailPage: its actions', () => {
  it('«Print / PDF» prints its A4 paper; a document of a sale is a copy', async () => {
    const s = await setup();
    await s.show({ ...INVOICE, source_type: 'sale' });
    expect(s.wrapper.findComponent(InvoicePaper).props()).toMatchObject({ duplicate: true });
    await click(s.find('invoice-detail-print').element);
    expect(mocks.print).toHaveBeenCalledOnce();
    expect((mocks.print.mock.calls[0][0] as HTMLElement).dataset.testid).toBe('invoice-paper');
  });

  it('«Mark as paid» asks and marks it; a refusal is said above the buttons', async () => {
    const s = await setup();
    await s.show(INVOICE);
    mocks.confirm.mockResolvedValue(true);
    s.answer(409, { error: { code: 'invoice.cannot_mark_paid', message: 'This invoice cannot be marked as paid.' } });
    await click(s.find('invoice-detail-mark-paid').element);
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/invoice/invoices/mark_paid', query: {}, body: { invoice_id: 'i1' } }]);
    expect(s.find('invoice-detail-error').text()).toContain('This invoice cannot be marked as paid.');
  });

  it('«Rectify» opens its window; «Full invoice» only on a ticket that can be replaced, and opens the new one', async () => {
    const s = await setup();
    await s.show(INVOICE);
    await click(s.find('invoice-detail-rectify').element);
    expect(s.wrapper.findComponent(RectifyModal).props('open')).toBe(true);
    expect(s.find('invoice-detail-substitute').exists()).toBe(false);
    await s.show({ ...INVOICE, invoice_type: 'F2', can_substitute: true });
    await click(s.find('invoice-detail-substitute').element);
    const modal = s.wrapper.findComponent(SubstituteModal);
    expect(modal.props('open')).toBe(true);
    const replace = vi.spyOn(s.router, 'push');
    modal.vm.$emit('substituted', { id: 'f3', number: 'FACT-2026-000002' });
    await flush();
    expect(replace).toHaveBeenCalledWith('/invoice/invoices/f3');
  });

  it('an employee does not rectify', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(INVOICE);
    expect(s.find('invoice-detail-mark-paid').exists()).toBe(true);
    expect(s.find('invoice-detail-rectify').exists()).toBe(false);
    expect(s.wrapper.findComponent(RectifyModal).exists()).toBe(false);
  });
});

describe('InvoiceDetailPage: the states of the screen', () => {
  it('an invoice that is not there says «Invoice not found»', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'invoice.not_found'));
    await flush();
    expect(s.find('invoice-detail-load-error').text()).toContain('Invoice not found');
  });

  it('another failure says it could not be loaded, with the server’s words', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(OP), 'invoice.boom'));
    await flush();
    expect(s.find('invoice-detail-load-error').text()).toContain('The invoice could not be loaded');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(INVOICE);
    expect([s.field('title'), s.field('status'), s.field('print'), s.field('issue-date')]).toEqual(['Factura FACT-2026-000001', 'Emitida', 'Imprimir / PDF', '14/10/2026']);
    expect(s.field('mark-paid')).toBe('Marcar pagada');
  });
});
