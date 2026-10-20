// The ticket of a sale as it prints (SALE-F29; the old `ok-receipt`): the header from the receipt
// settings (first line = the name, else «My business»; the rest = the address), «DUPLICATE» on every
// reprint, the number and the date and time, the customer, the lines («qty × unit price», a gift
// «(On the house)», the note), «Subtotal», the VAT rows by rate from the sale's breakdown, «TOTAL», the
// payment rows and «Change», the discount already applied and the footer. No fiscal QR: the invoice
// number and the VeriFactu QR arrive with Invoicing and VeriFactu.
import { formatDateTime } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { saleOut, SETTINGS, SUBJECT_VAT } from './__tests__/fixtures';
import ReceiptPaper from './ReceiptPaper.vue';
import source from './ReceiptPaper.vue?raw';

/** What a person reads in `el`: its texts in order, one space apart (cells and lines are blocks). */
function words(el: Element): string {
  const out: string[] = [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = plain(node.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (text) out.push(text);
  }
  return out.join(' ');
}

async function paper(props: Record<string, unknown>, locale: 'en' | 'es' = 'es') {
  const m = await mountSale(ReceiptPaper, { props, locale });
  const text = (testid: string) => plain(m.find(testid).text());
  const all = (testid: string) => m.wrapper.findAll(`[data-testid="${testid}"]`).map((el) => words(el.element));
  return { ...m, text, all };
}

describe('ReceiptPaper', () => {
  it('heads with the receipt header: its first line is the name, the rest the address', async () => {
    const s = await paper({ sale: saleOut(), settings: SETTINGS });
    expect(s.text('sale-receipt-name')).toBe('Bar Pepe');
    expect(s.all('sale-receipt-address')).toEqual(['Calle Mayor 1', 'Madrid']);
  });

  it('a sale charged as an invoice is titled «Invoice» and numbered «No.», never «Receipt»', async () => {
    const s = await paper({ sale: saleOut({ document_type: 'invoice' }), settings: SETTINGS });
    expect(s.text('sale-receipt-title')).toBe('Factura');
    expect(s.text('sale-receipt-number')).toBe('Nº: 20261014-0007');
    const en = await paper({ sale: saleOut({ document_type: 'invoice' }), settings: SETTINGS }, 'en');
    expect([en.text('sale-receipt-title'), en.text('sale-receipt-number')]).toEqual(['Invoice', 'No.: 20261014-0007']);
    const ticket = await paper({ sale: saleOut(), settings: SETTINGS });
    expect(ticket.find('sale-receipt-title').exists()).toBe(false);
    expect(ticket.text('sale-receipt-number')).toBe('Tiquet: 20261014-0007');
  });

  it('prints the number Invoicing gave it: «Invoice <series number>» or the ticket’s, never the sale’s', async () => {
    const invoice = saleOut({ document_type: 'invoice', invoice_status: 'issued', invoice_type: 'F1', invoice_number: 'FACT-2026-000012' });
    const s = await paper({ sale: invoice, settings: SETTINGS });
    expect([s.text('sale-receipt-title'), s.text('sale-receipt-number')]).toEqual(['Factura', 'Factura: FACT-2026-000012']);
    const en = await paper({ sale: invoice, settings: SETTINGS }, 'en');
    expect(en.text('sale-receipt-number')).toBe('Invoice: FACT-2026-000012');
    const ticket = saleOut({ invoice_status: 'issued', invoice_type: 'F2', invoice_number: 'TICKET-2026-000031' });
    expect((await paper({ sale: ticket, settings: SETTINGS })).text('sale-receipt-number')).toBe('Tiquet: TICKET-2026-000031');
  });

  it('a ticket whose fiscal document waits says so under its number (never posing as issued)', async () => {
    const s = await paper({ sale: saleOut({ invoice_status: 'pending', invoice_number: '', invoice_type: '' }), settings: SETTINGS });
    expect(s.text('sale-receipt-pending')).toBe('Documento fiscal pendiente');
    const issued = await paper({ sale: saleOut({ invoice_status: 'issued', invoice_number: 'TICKET-2026-000001' }), settings: SETTINGS });
    expect(issued.find('sale-receipt-pending').exists()).toBe(false);
  });

  it('a VAT row per fiscal key: an exempt key names its cause and never merges with a 0 % one', async () => {
    const s = await paper({
      sale: saleOut({
        breakdown: [
          { ...SUBJECT_VAT, rate_pct: '10.00', label: 'vat', base: 273, tax: 27 },
          { ...SUBJECT_VAT, rate_pct: '0.00', label: 'vat', base: 500, tax: 0 },
          { ...SUBJECT_VAT, qualification: 'exempt', exempt_reason: 'E1', rate_pct: '0.00', label: 'vat', base: 4000, tax: 0 },
        ],
      }),
      settings: SETTINGS,
    });
    expect(s.all('sale-receipt-total-row').slice(1, 4)).toEqual(['IVA 10 % 0,27 €', 'IVA 0 % 0,00 €', 'Exento (E1) 0,00 €']);
  });

  it('without a header the name is «My business»', async () => {
    const s = await paper({ sale: saleOut(), settings: { receipt_header: '  \n', receipt_footer: '' } });
    expect(s.text('sale-receipt-name')).toBe('Mi negocio');
    expect(s.find('sale-receipt-address').exists()).toBe(false);
    const en = await paper({ sale: saleOut(), settings: null }, 'en');
    expect(en.text('sale-receipt-name')).toBe('My business');
  });

  it('says the sale’s number with its date and time, and the customer when there is one', async () => {
    const s = await paper({ sale: saleOut({ customer_name: 'Lucía Pérez' }), settings: SETTINGS });
    expect(s.text('sale-receipt-number')).toBe('Tiquet: 20261014-0007');
    expect(s.text('sale-receipt-datetime')).toBe(plain(formatDateTime('2026-10-14T10:05:00Z', 'es')));
    expect(s.text('sale-receipt-customer')).toBe('Cliente: Lucía Pérez');
    const anonymous = await paper({ sale: saleOut(), settings: SETTINGS });
    expect(anonymous.find('sale-receipt-customer').exists()).toBe(false);
  });

  it('lists every line: name, «qty × unit price», its note, a gift «(On the house)», and its amount', async () => {
    const s = await paper({ sale: saleOut(), settings: SETTINGS });
    expect(s.all('sale-receipt-line')).toEqual([
      'Café con leche 2 × 1,50 € sin azúcar 3,00 €',
      'Tarta (Invitación) 1 × 4,50 € 0,00 €',
      'Queso 0,532 kg × 18,00 € 9,50 €',
    ]);
    expect(s.all('sale-receipt-head')).toEqual(['Concepto Importe']);
  });

  it('a line a voucher paid says «Already paid · <voucher>» at 0,00 € (SALE-F27)', async () => {
    const sale = saleOut();
    const cut = { ...sale.lines[0], id: 'l9', name: 'Corte', quantity: '1.000', unit_price: 2500, notes: '', line_total: 0, paid_by_voucher: true, voucher_name: 'Bono 5 cortes' };
    const s = await paper({ sale: { ...sale, lines: [cut] }, settings: SETTINGS });
    expect(s.all('sale-receipt-line')).toEqual(['Corte 1 × 25,00 € Ya pagado · Bono 5 cortes 0,00 €']);
  });

  it('prints the options of a dish under it and an option of another tax as its own line under the dish (SALE-F11)', async () => {
    const sale = saleOut();
    const burger = { ...sale.lines[0], id: 'b1', name: 'Hamburguesa', quantity: '2.000', unit_price: 900, notes: '', line_total: 1800, modifiers: ['Queso', 'Poco hecha'] };
    const soda = { ...sale.lines[0], id: 'b2', name: 'Refresco', quantity: '2.000', unit_price: 200, notes: '', line_total: 400, parent_line_id: 'b1' };
    const s = await paper({ sale: { ...sale, lines: [burger, soda] }, settings: SETTINGS });
    expect(s.all('sale-receipt-line')).toEqual(['Hamburguesa 2 × 9,00 € Queso, Poco hecha 18,00 €', '+ Refresco 2 × 2,00 € 4,00 €']);
  });

  it('a sale without lines says so', async () => {
    const s = await paper({ sale: saleOut({ lines: [] }), settings: SETTINGS });
    expect(s.text('sale-receipt-no-lines')).toBe('— Sin líneas —');
  });

  it('adds up: Subtotal, a VAT row per rate, TOTAL, how it was paid and the change', async () => {
    const s = await paper({
      sale: saleOut({
        breakdown: [
          { ...SUBJECT_VAT, rate_pct: '10.00', label: 'vat', base: 1136, tax: 114 },
          { ...SUBJECT_VAT, tax_type: 'surcharge', rate_pct: '1.40', label: 'surcharge', base: 1136, tax: 12 },
        ],
      }),
      settings: SETTINGS,
    });
    expect(s.all('sale-receipt-total-row')).toEqual([
      'Subtotal 11,24 €',
      'IVA 10 % 1,14 €',
      'RE 1,4 % 0,12 €',
      'TOTAL 12,50 €',
      'Efectivo 20,00 €',
      'Cambio 7,50 €',
    ]);
  });

  it('a card payment shows what it charged and no change; several tenders, one row each', async () => {
    const s = await paper({
      sale: saleOut({
        tendered_total: 1250,
        change_total: 0,
        payments: [
          { id: 'p1', position: 1, method_id: 'm2', method_name: 'Tarjeta', method_type: 'card', amount: 1000, tendered: 1000, change: 0, reference: '' },
          { id: 'p2', position: 2, method_id: 'm3', method_name: 'Bizum', method_type: 'other', amount: 250, tendered: 250, change: 0, reference: '' },
        ],
      }),
      settings: SETTINGS,
    });
    expect(s.all('sale-receipt-total-row').slice(-2)).toEqual(['Tarjeta 10,00 €', 'Bizum 2,50 €']);
  });

  it('a tax it has no short name for keeps the one the rule gave it', async () => {
    const s = await paper({ sale: saleOut({ breakdown: [{ ...SUBJECT_VAT, rate_pct: '7.00', label: 'Tasa turística', base: 100, tax: 7 }] }), settings: SETTINGS });
    expect(s.all('sale-receipt-total-row')[1]).toBe('Tasa turística 7 % 0,07 €');
  });

  it('ends with the discount already applied and the receipt footer', async () => {
    const s = await paper({ sale: saleOut({ discount_amount: 200 }), settings: SETTINGS });
    expect(s.all('sale-receipt-footer')).toEqual(['Descuento de 2,00 €, ya aplicado en los importes de arriba.', '¡Gracias por su visita!']);
    const bare = await paper({ sale: saleOut(), settings: { receipt_header: '', receipt_footer: '' } });
    expect(bare.find('sale-receipt-footer').exists()).toBe(false);
  });

  it('a reprint says «DUPLICATE» on top; the original does not', async () => {
    const copy = await paper({ sale: saleOut(), settings: SETTINGS, duplicate: true });
    expect(copy.text('sale-receipt-duplicate')).toBe('DUPLICADO');
    const original = await paper({ sale: saleOut(), settings: SETTINGS });
    expect(original.find('sale-receipt-duplicate').exists()).toBe(false);
  });

  it('carries no fiscal QR (VeriFactu arrives with its app) and no OutfitKit', () => {
    expect(source).not.toMatch(/<ok[-]/);
    expect(source).not.toMatch(/VERI\*FACTU|QR tributario/);
  });

  it('speaks English', async () => {
    const s = await paper({ sale: saleOut({ customer_name: 'Lucía' }), settings: SETTINGS, duplicate: true }, 'en');
    expect(s.text('sale-receipt-number')).toBe('Receipt: 20261014-0007');
    expect(s.text('sale-receipt-duplicate')).toBe('DUPLICATE');
    expect(s.all('sale-receipt-line')[1]).toBe('Tarta (On the house) 1 × €4.50 €0.00');
    expect(s.all('sale-receipt-total-row')).toEqual(['Subtotal €11.24', 'VAT 10% €1.14', 'TOTAL €12.50', 'Efectivo €20.00', 'Change €7.50']);
  });
});
