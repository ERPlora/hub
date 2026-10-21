// The A4 paper of an invoice (INVOICE-F18; the old `<ok-invoice>` and the server's
// `templates/invoice/invoice.html`, same layout): the issuer and the document block (title by kind,
// «Copy» on a reprint, number, date and, when it differs, the operation date), «Bill to», the lines, the
// breakdown with its bases, the totals and the note of what it rectifies — in the page's language.
import { describe, expect, it } from 'vitest';

import { mountInvoice } from '../__tests__/mount-invoice';
import { plain } from '../lib/format';
import type { InvoiceOut } from '../operations';
import InvoicePaper from './InvoicePaper.vue';

const INVOICE = {
  id: 'i1',
  number: 'FACT-2026-000001',
  invoice_type: 'F1',
  issue_date: '2026-10-14',
  operation_date: '2026-10-13',
  issuer_name: 'Peluquería Ana SL',
  issuer_tax_id: 'B12345674',
  issuer_address: 'Calle Mayor 1, 28001 Madrid (Madrid)',
  customer_name: 'Talleres Pérez SL',
  customer_tax_id: 'B12345674',
  customer_address: 'Calle Luna 3',
  customer_country: '',
  notes: 'Thanks',
  description: '',
  rectifies: null,
  base_amount: 2000,
  tax_amount: 420,
  total_amount: 2420,
  tax_breakdown: [{ tax: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', rate: '21.00', surcharge_rate: '0.00', base: 2000, quota: 420, surcharge_quota: 0 }],
  lines: [{ id: 'l1', position: 1, description: 'Course', quantity: '2.000', unit_price: '1000.00', discount_amount: 0, tax_rate: '21.00', surcharge_rate: '0.00', tax_category_key: '', base_amount: 2000, tax_amount: 420, total_amount: 2420, product_id: null }],
} as unknown as InvoiceOut;

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(InvoicePaper, { props: { invoice: INVOICE, ...props }, locale });
  const text = (testid: string) => plain(m.find(testid).text());
  return { ...m, text };
}

describe('InvoicePaper', () => {
  it('is the A4 sheet: issuer, document block, bill to, lines, breakdown, totals and note', async () => {
    const s = await setup();
    expect(s.text('invoice-paper-issuer')).toContain('Peluquería Ana SL');
    expect(s.text('invoice-paper-issuer')).toContain('Tax ID: B12345674');
    expect(s.text('invoice-paper-title')).toBe('Invoice');
    expect(s.find('invoice-paper-copy').exists()).toBe(false);
    expect(s.text('invoice-paper-number')).toBe('FACT-2026-000001');
    expect(s.text('invoice-paper-date')).toBe('10/14/2026');
    expect(s.text('invoice-paper-operation-date')).toBe('10/13/2026');
    expect(s.text('invoice-paper-bill-to')).toContain('Talleres Pérez SL');
    expect(s.wrapper.findAll('[data-testid="invoice-paper-line"]').map((row) => row.findAll('td').map((td) => plain(td.text())))).toEqual([
      ['Course', '2', '€10.00', '21%', '€20.00'],
    ]);
    expect(s.text('invoice-paper-taxes')).toContain('VAT 21% (€20.00)');
    expect(s.text('invoice-paper-total')).toBe('€24.20');
    expect(s.text('invoice-paper-note')).toBe('Thanks');
  });

  it('prints each unit price WITHOUT VAT (up to four decimals) and a discount apart (RD 1619/2012 art. 6.1.f)', async () => {
    const discounted = {
      ...INVOICE,
      lines: [
        { ...INVOICE.lines[0], unit_price: '1000.00', discount_amount: 200, base_amount: 1800, tax_amount: 378, total_amount: 2178 },
        { ...INVOICE.lines[0], id: 'l2', description: 'Gum', quantity: '3.000', unit_price: '41.32', discount_amount: 0, base_amount: 124, tax_amount: 26, total_amount: 150 },
      ],
    } as unknown as InvoiceOut;
    const s = await setup({ invoice: discounted });
    const headers = s.wrapper.findAll('.invoice-paper__lines th').map((th) => plain(th.text()));
    expect(headers).toEqual(['Description', 'Qty', 'Price', 'Disc.', 'Tax', 'Amount']);
    expect(s.wrapper.findAll('[data-testid="invoice-paper-line"]').map((row) => row.findAll('td').map((td) => plain(td.text())))).toEqual([
      ['Course', '2', '€10.00', '€2.00', '21%', '€18.00'],
      ['Gum', '3', '€0.4132', '', '21%', '€1.24'],
    ]);
    const es = await setup({ invoice: discounted }, 'es');
    expect(es.wrapper.findAll('[data-testid="invoice-paper-line"]')[1].findAll('td').map((td) => plain(td.text()))[2]).toBe('0,4132 €');
  });

  it('a ticket is a simplified invoice without «Bill to»; a reprint says «Copy»', async () => {
    const s = await setup({ invoice: { ...INVOICE, invoice_type: 'F2', customer_name: '', customer_tax_id: '' }, duplicate: true });
    expect(s.text('invoice-paper-title')).toBe('Simplified invoice');
    expect(s.text('invoice-paper-copy')).toBe('Copy');
    expect(s.find('invoice-paper-bill-to').exists()).toBe(false);
  });

  it('a rectifying invoice names what it rectifies and why', async () => {
    const s = await setup({ invoice: { ...INVOICE, invoice_type: 'R1', description: 'Wrong price', rectifies: { id: 'o', number: 'FACT-2026-000001' } } });
    expect(s.text('invoice-paper-title')).toBe('Rectifying invoice');
    expect(s.text('invoice-paper-note')).toBe('Rectifies invoice FACT-2026-000001. Reason: Wrong price');
  });

  it('with its VeriFactu record carries the AEAT’s QR on top, in the AEAT’s words (Orden HAC/1177/2024, art. 21)', async () => {
    const s = await setup({ record: { qr_svg: 'data:image/svg+xml;base64,PHN2Zy8+', qr_url: 'https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674' } });
    const qr = s.find('invoice-paper-qr');
    expect(qr.text()).toContain('QR tributario:');
    expect(qr.text()).toContain('VERI*FACTU');
    expect(qr.find('img').attributes('src')).toBe('data:image/svg+xml;base64,PHN2Zy8+');
    // The QR is the first thing of the sheet, as on the server's paper.
    expect(s.wrapper.find('[data-testid="invoice-paper"]').element.firstElementChild?.getAttribute('data-testid')).toBe('invoice-paper-qr');
  });

  it('without a record carries no QR', async () => {
    expect((await setup()).find('invoice-paper-qr').exists()).toBe(false);
    expect((await setup({ record: null })).find('invoice-paper-qr').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ duplicate: true }, 'es');
    expect([s.text('invoice-paper-title'), s.text('invoice-paper-copy'), s.text('invoice-paper-date')]).toEqual(['Factura', 'Copia', '14/10/2026']);
    expect(s.text('invoice-paper-bill-to')).toContain('Facturar a');
    expect(s.text('invoice-paper-total')).toBe('24,20 €');
  });
});
