// The open invoice (INVOICE-F17, F18, F19, F05, F08; the old detail of `erp-invoice-list`): «Invoice
// <number>» with its status, «Print / PDF» and «Back»; the warning of a full invoice without the customer's
// tax ID; Type, Series, Issue date (and Operation date when it differs), Customer, tax ID, Address, Issuer,
// Source, Sale, the documents it rectifies or replaces or is replaced or rectified by (each opens), Paid on
// and Notes; the lines, the breakdown and the totals; «Mark as paid», «Rectify» and «Full invoice» where
// they apply and for whoever may. It follows `invoice.invoice.get` live: a payment or a rectification made
// elsewhere shows by itself.
import { AppPage, toastError, toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { INVOICE, OP, setup } from '../__tests__/invoice-detail';
import { click, EMPLOYEE, errorFrame, flush, type MountOptions, OWNER } from '../__tests__/mount-invoice';
import InvoiceLinesTable from '../components/InvoiceLinesTable.vue';
import InvoicePaper from '../components/InvoicePaper.vue';
import RectifyModal from '../components/RectifyModal.vue';
import SubstituteModal from '../components/SubstituteModal.vue';
import { PrintRefused } from '../../../../base/frontend/lib/print-paper';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), print: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('../../../sale/frontend/lib/print', () => ({ printPaper: mocks.print }));
beforeEach(() => {
  mocks.confirm.mockReset();
  mocks.print.mockReset();
});

/** What `invoice.invoice.print` answers when no system printer takes the page: the screen prints its own paper. */
const NO_PRINTER = { error: { code: 'invoice.no_printer', message: 'No system printer takes this invoice.' } };

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
    // The rate is named by the tax the invoice declares (its breakdown): VAT here.
    expect(s.wrapper.findComponent(InvoiceLinesTable).props('taxes')).toEqual(['vat']);
    expect(s.find('invoice-missing-tax-id').exists()).toBe(false);
  });

  it('says when it falls due, if it does, and «Overdue» instead of «Issued» once it has passed', async () => {
    const s = await setup();
    await s.show(INVOICE);
    expect(s.find('invoice-detail-due-date').exists()).toBe(false);
    await s.show({ ...INVOICE, due_date: '2026-11-13', overdue: true });
    expect([s.field('due-date'), s.field('status')]).toEqual(['11/13/2026', 'Overdue']);
    expect(s.find('invoice-detail-status').attributes('data-tone')).toBe('warning');
    expect(s.find('invoice-detail-due-date').element.previousElementSibling?.textContent).toBe('Due date');
  });

  it('names the issuer with the tax ID its document prints: the EU VAT number of one in the ROI', async () => {
    const s = await setup();
    await s.show({ ...INVOICE, issuer_vat_number: 'ESB12345674' });
    expect(s.field('issuer')).toBe('Peluquería Ana SL (ESB12345674)');
  });

  it('names the rate column by the tax the invoice declares: IGIC for a business of the Canary Islands', async () => {
    const s = await setup();
    await s.show({ ...INVOICE, tax_breakdown: INVOICE.tax_breakdown.map((entry) => ({ ...entry, tax: 'igic', rate: '7.00' })) });
    expect(s.wrapper.findComponent(InvoiceLinesTable).props('taxes')).toEqual(['igic']);
    expect(s.wrapper.findComponent(InvoiceLinesTable).findAll('th').map((th) => th.text())).toContain('IGIC %');
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
    s.answer(409, NO_PRINTER);
    await click(s.find('invoice-detail-print').element);
    await flush();
    expect(mocks.print).toHaveBeenCalledOnce();
    expect((mocks.print.mock.calls[0][0] as HTMLElement).dataset.testid).toBe('invoice-paper');
    // Titled: the print job's name and the file «Save as PDF» proposes (hub#455).
    expect(mocks.print.mock.calls[0][1]).toEqual({ title: 'Invoice FACT-2026-000001' });
  });

  it('in the installed app, a print the app refuses says why (hub#455)', async () => {
    const s = await setup();
    await s.show(INVOICE);
    s.answer(409, NO_PRINTER);
    mocks.print.mockRejectedValueOnce(new PrintRefused('refused', 'print_document_refused'));
    await click(s.find('invoice-detail-print').element);
    await flush();
    expect(toastError).toHaveBeenCalledExactlyOnceWith('Could not print the invoice: the document is empty or too large to print');
  });

  it('a second press while the app prints waits for it (hub#455)', async () => {
    const s = await setup();
    await s.show(INVOICE);
    s.answer(409, NO_PRINTER);
    let done = (): void => {};
    mocks.print.mockReturnValueOnce(new Promise<void>((resolve) => (done = resolve)));
    await click(s.find('invoice-detail-print').element);
    await flush();
    await click(s.find('invoice-detail-print').element);
    await flush();
    expect(mocks.print).toHaveBeenCalledOnce();
    done();
    await flush();
    await click(s.find('invoice-detail-print').element);
    await flush();
    expect(mocks.print).toHaveBeenCalledTimes(2);
  });

  it('«Print / PDF» asks the printing queue first: queued, a toast names the printer and the screen prints nothing', async () => {
    const s = await setup();
    await s.show({ ...INVOICE, source_type: 'sale' });
    s.answer(200, { job_id: 'j1', printer: 'Office' });
    await click(s.find('invoice-detail-print').element);
    await flush();
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/invoice/invoices/print', query: {}, body: { invoice_id: 'i1', duplicate: true } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Sent to Office.');
    expect(mocks.print).not.toHaveBeenCalled();
  });

  it('no printer takes it, or the queue out of reach: the browser prints the A4 paper', async () => {
    const answers = [
      [409, NO_PRINTER],
      [503, { error: { code: 'unavailable', message: 'down' } }],
    ] as const;
    for (const [status, body] of answers) {
      mocks.print.mockReset();
      const s = await setup();
      await s.show(INVOICE);
      s.answer(status, body);
      await click(s.find('invoice-detail-print').element);
      await flush();
      expect(s.sent().find((call) => call.path === '/api/invoice/invoices/print')?.body).toEqual({ invoice_id: 'i1', duplicate: false });
      expect(mocks.print).toHaveBeenCalledOnce();
      expect(toastSuccess).not.toHaveBeenCalled();
      s.wrapper.unmount();
    }
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

describe('InvoiceDetailPage: its VeriFactu record (INVOICE-F17, F18; VERIFACTU-F19)', () => {
  const RECORD_OP = 'verifactu.record.by_invoice';
  const WITH_VERIFACTU = { ...OWNER, permissions: [...OWNER.permissions, 'verifactu.view_record'], apps: [{ label: 'verifactu', state: 'on' as const }] };
  const RECORD = {
    id: 'r1',
    invoice_id: 'i1',
    invoice_number: 'FACT-2026-000001',
    record_type: 'alta',
    invoice_type: 'F1',
    sequence: 1,
    environment: 'production',
    status: 'accepted',
    fingerprint: 'ABC',
    qr_url: 'https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674',
    qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+',
    csv: 'A-ZGTHW2SE4KQ8B2',
  };

  /** The invoice and its record on the same stream, from the first one: no reopen (an aborted stream). */
  async function withRecord(options: MountOptions = {}) {
    const s = await setup({ session: WITH_VERIFACTU, ...options });
    await s.show(INVOICE);
    // Past the SDK's 150 ms debounce: had the record been asked for later, the stream would have reopened.
    await s.reopen();
    expect(s.net.streams).toHaveLength(1);
    return s;
  }

  it('follows the record of the invoice and shows its receipt; the paper carries its QR', async () => {
    const s = await withRecord();
    expect(s.params(RECORD_OP)).toEqual([{ invoice_id: 'i1' }]);
    await s.result(RECORD_OP, { record: RECORD });
    expect(s.find('invoice-verifactu').exists()).toBe(true);
    expect(s.wrapper.findComponent(InvoicePaper).props('record')).toMatchObject({ qr_svg: RECORD.qr_svg, qr_url: RECORD.qr_url });
  });

  it('without a record yet there is no receipt and the paper has no QR', async () => {
    const s = await withRecord();
    await s.result(RECORD_OP, { record: null });
    expect(s.find('invoice-verifactu').exists()).toBe(false);
    expect(s.wrapper.findComponent(InvoicePaper).props('record')).toBeNull();
    s.answer(409, NO_PRINTER);
    await click(s.find('invoice-detail-print').element);
    await flush();
    expect(mocks.print).toHaveBeenCalledOnce();
  });

  it('asks nothing with VeriFactu off or without the right to read its records', async () => {
    for (const session of [OWNER, { ...WITH_VERIFACTU, permissions: OWNER.permissions }]) {
      const s = await setup({ session });
      await s.show(INVOICE);
      await s.reopen();
      expect(s.params(RECORD_OP)).toEqual([]);
      expect(s.find('invoice-verifactu').exists()).toBe(false);
      s.wrapper.unmount();
    }
  });

  it('never prints on screen without the QR: «Print / PDF» waits for the record, and a record it cannot read prints nothing', async () => {
    const s = await withRecord();
    const disabled = () => (s.find('invoice-detail-print').element as HTMLElement & { disabled: boolean }).disabled;
    expect(disabled()).toBe(true);
    s.call.push(errorFrame(s.subId(RECORD_OP), 'verifactu.boom'));
    await flush();
    expect(s.find('invoice-verifactu').exists()).toBe(false);
    expect(disabled()).toBe(false);
    s.answer(409, { error: { code: 'invoice.record_unreadable', message: 'Its VeriFactu record could not be read.' } });
    await click(s.find('invoice-detail-print').element);
    await flush();
    expect(mocks.print).not.toHaveBeenCalled();
    expect(toastError).toHaveBeenCalledWith('Could not print the invoice');
  });
});
