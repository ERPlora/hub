// The breakdown and the totals of an open invoice (INVOICE-F17): one row per tax of the breakdown with its
// base and its amount («VAT 21%», «Equivalence surcharge 5.2%», «Exempt (E1)»…), then «Base», «Taxes» and
// «Total», the server's figures in the page's language.
import { describe, expect, it } from 'vitest';

import { mountInvoice } from '../__tests__/mount-invoice';
import { plain } from '../lib/format';
import type { BreakdownOut } from '../operations';
import InvoiceTotals from './InvoiceTotals.vue';

const entry = (over: Partial<BreakdownOut> = {}): BreakdownOut => ({
  tax: 'vat',
  regime: '01',
  qualification: 'subject',
  exempt_reason: '',
  rate: '21.00',
  surcharge_rate: '0.00',
  base: 2000,
  quota: 420,
  surcharge_quota: 0,
  ...over,
});

const INVOICE = {
  tax_breakdown: [entry({ surcharge_rate: '5.20', surcharge_quota: 104 }), entry({ qualification: 'exempt', exempt_reason: 'E1', rate: '0.00', base: 4000, quota: 0 })],
  base_amount: 6000,
  tax_amount: 524,
  total_amount: 6524,
};

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(InvoiceTotals, { props: { invoice: INVOICE }, locale });
  const taxes = () =>
    m.wrapper
      .findAll('[data-testid="invoice-detail-tax"]')
      .map((row) => `${plain(row.find('[data-testid="invoice-detail-tax-label"]').text())} = ${plain(row.find('[data-testid="invoice-detail-tax-amount"]').text())}`);
  return { ...m, taxes };
}

describe('InvoiceTotals', () => {
  it('paints each tax of the breakdown with its base, then the totals', async () => {
    const s = await setup();
    expect(s.taxes()).toEqual(['VAT 21% (€20.00) = €4.20', 'Equivalence surcharge 5.2% (€20.00) = €1.04', 'Exempt (E1) (€40.00) = €0.00']);
    expect(plain(s.find('invoice-detail-base').text())).toBe('Base: €60.00');
    expect(plain(s.find('invoice-detail-taxes').text())).toBe('Taxes: €5.24');
    expect(plain(s.find('invoice-detail-total').text())).toBe('Total: €65.24');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.taxes()[0]).toBe('IVA 21 % (20,00 €) = 4,20 €');
    expect(plain(s.find('invoice-detail-taxes').text())).toBe('Impuestos: 5,24 €');
  });
});
