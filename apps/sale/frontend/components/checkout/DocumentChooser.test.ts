// SALE-F04 step 1: «Receipt» or «Invoice», two big buttons side by side in a group named «Document», the
// chosen one pressed. It only chooses; the sheet decides what it starts on and hides it over the limit.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import DocumentChooser from './DocumentChooser.vue';

async function setup(modelValue: 'ticket' | 'invoice' = 'ticket', locale: 'en' | 'es' = 'en') {
  const m = await mountSale(DocumentChooser, { props: { modelValue }, locale });
  const ticket = () => m.find('sale-checkout-doc-ticket');
  const invoice = () => m.find('sale-checkout-doc-invoice');
  return { ...m, ticket, invoice };
}

describe('DocumentChooser', () => {
  it('offers Receipt and Invoice in a group named «Document», the chosen one pressed', async () => {
    const s = await setup('invoice');
    expect(s.find('sale-checkout-doc').attributes()).toMatchObject({ role: 'group', 'aria-label': 'Document' });
    expect([s.ticket().text(), s.ticket().attributes('aria-pressed')]).toEqual(['Receipt', 'false']);
    expect([s.invoice().text(), s.invoice().attributes('aria-pressed')]).toEqual(['Invoice', 'true']);
  });

  it('chooses with a tap', async () => {
    const s = await setup('ticket');
    await click(s.invoice().element);
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['invoice']]);
  });

  it('speaks Spanish: Tique and Factura', async () => {
    const s = await setup('ticket', 'es');
    expect([s.find('sale-checkout-doc').attributes('aria-label'), s.ticket().text(), s.invoice().text()]).toEqual(['Documento', 'Tique', 'Factura']);
  });
});
