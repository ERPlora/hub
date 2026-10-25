// The lines of an open invoice (INVOICE-F17; the old detail's table): «#», «Description», «Qty», «Price»
// (WITHOUT VAT, RD 1619/2012 art. 6.1.f), «Disc.» when a line has one, the rate named by the tax the invoice
// declares («VAT %», «IGIC %», «IPSI %»; «Tax %» when it mixes them), «Base», «Tax», «Total», every
// amount the server's in the page's language (a rectifying line with its sign; a surcharge next to its rate).
// Narrow, each line is a block whose cells name their column. Without lines, «No detail lines.».
import { describe, expect, it } from 'vitest';

import { mountInvoice } from '../__tests__/mount-invoice';
import { plain } from '../lib/format';
import type { InvoiceLineOut } from '../operations';
import InvoiceLinesTable from './InvoiceLinesTable.vue';

const line = (over: Partial<InvoiceLineOut> = {}): InvoiceLineOut => ({
  id: 'l1',
  position: 1,
  description: 'Shampoo',
  quantity: '2.000',
  unit_price: '1000.00',
  discount_amount: 0,
  tax_rate: '21.00',
  surcharge_rate: '0.00',
  tax_category_key: 'product.generic',
  base_amount: 2000,
  tax_amount: 420,
  total_amount: 2420,
  product_id: null,
  ...over,
});

async function setup(lines: InvoiceLineOut[], locale: 'en' | 'es' = 'en', taxes: string[] = ['vat'], currency = 'EUR') {
  const m = await mountInvoice(InvoiceLinesTable, { props: { lines, taxes, currency }, locale });
  const cells = () => m.wrapper.findAll('[data-testid="invoice-line-row"]').map((row) => row.findAll('td').map((td) => plain(td.text())));
  return { ...m, cells };
}

describe('InvoiceLinesTable', () => {
  it('paints the eight columns of each line with the server’s figures', async () => {
    const s = await setup([line(), line({ id: 'l2', position: 2, description: 'Wax', quantity: '-1.000', unit_price: '500.00', tax_rate: '21.00', surcharge_rate: '5.20', base_amount: -500, tax_amount: -131, total_amount: -631 })]);
    expect(s.wrapper.findAll('th').map((th) => th.text())).toEqual(['#', 'Description', 'Qty', 'Price', 'VAT %', 'Base', 'Tax', 'Total']);
    expect(s.cells()).toEqual([
      ['1', 'Shampoo', '2', '€10.00', '21%', '€20.00', '€4.20', '€24.20'],
      ['2', 'Wax', '-1', '€5.00', '21% + 5.2%', '-€5.00', '-€1.31', '-€6.31'],
    ]);
    // Narrow, every cell says its column.
    expect(s.wrapper.findAll('[data-testid="invoice-line-row"] td').map((td) => td.attributes('data-label')).slice(0, 8)).toEqual([
      '#',
      'Description',
      'Qty',
      'Price',
      'VAT %',
      'Base',
      'Tax',
      'Total',
    ]);
  });

  it('names the rate by the tax the invoice declares: IGIC or IPSI in their territories, «Tax %» when mixed', async () => {
    const header = async (taxes: string[], locale: 'en' | 'es' = 'en') => (await setup([line()], locale, taxes)).wrapper.findAll('th')[4].text();
    expect(await header(['igic'])).toBe('IGIC %');
    expect(await header(['ipsi', 'ipsi'])).toBe('IPSI %');
    expect(await header(['igic', 'vat'])).toBe('Tax %');
    expect(await header(['igic'], 'es')).toBe('IGIC %');
    expect(await header(['igic', 'vat'], 'es')).toBe('Imp. %');
  });

  it('without lines says «No detail lines.»', async () => {
    const s = await setup([]);
    expect(s.find('invoice-detail-no-lines').text()).toBe('No detail lines.');
    expect(s.find('invoice-detail-lines').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup([line()], 'es');
    expect(s.wrapper.findAll('th').map((th) => th.text())).toEqual(['#', 'Descripción', 'Cant.', 'Precio', 'IVA %', 'Base', 'Impuesto', 'Total']);
    expect(s.cells()[0].slice(3)).toEqual(['10,00 €', '21 %', '20,00 €', '4,20 €', '24,20 €']);
  });

  it('shows the discount apart when a line has one, the price before it', async () => {
    const s = await setup([line({ discount_amount: 200, base_amount: 1800, tax_amount: 378, total_amount: 2178 }), line({ id: 'l2', position: 2 })]);
    expect(s.wrapper.findAll('th').map((th) => th.text())).toEqual(['#', 'Description', 'Qty', 'Price', 'Disc.', 'VAT %', 'Base', 'Tax', 'Total']);
    expect(s.cells()).toEqual([
      ['1', 'Shampoo', '2', '€10.00', '€2.00', '21%', '€18.00', '€3.78', '€21.78'],
      ['2', 'Shampoo', '2', '€10.00', '', '21%', '€20.00', '€4.20', '€24.20'],
    ]);
  });

  it('paints a line of an invoice in zlotys in zlotys (flow business-currency)', async () => {
    const s = await setup([line()], 'en', ['vat'], 'PLN');
    expect(s.cells()[0]).toContain('PLN 24.20');
    expect(s.cells()[0].join(' ')).not.toContain('€');
  });
});
