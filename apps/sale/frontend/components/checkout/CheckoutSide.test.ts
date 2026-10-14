// The side group of the charge sheet (SALE-F04): what the sale is — «Receipt» or «Invoice» and, with an
// invoice, who it is for. Over the ticket limit there is no «Receipt»: «This sale cannot be a ticket» and
// the same details. On a phone it folds into one summary line («Invoice · Bar Pepe SL») that opens with
// a tap; choosing «Invoice» opens it, since it asks something right below.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import type { Recipient } from '../../lib/checkout/recipient';
import CheckoutSide from './CheckoutSide.vue';
import DocumentChooser from './DocumentChooser.vue';
import RecipientForm from './RecipientForm.vue';

const RECIPIENT: Recipient = { name: 'Bar Pepe SL', taxId: '', address: '', country: 'ES', idType: '' };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(CheckoutSide, {
    props: { document: 'ticket', overLimit: false, ticketLimit: 300000, recipient: RECIPIENT, open: false, ...props },
    locale,
  });
  for (const name of ['document', 'recipient', 'open']) {
    await m.wrapper.setProps({ [`onUpdate:${name}`]: (value: unknown) => m.wrapper.setProps({ [name]: value }) });
  }
  const side = () => m.find('sale-checkout-side');
  const summary = () => m.find('sale-checkout-summary');
  const form = () => m.wrapper.findComponent(RecipientForm);
  return { ...m, side, summary, form };
}

describe('CheckoutSide', () => {
  it('a receipt: just the choice, nothing to fold', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(DocumentChooser).props('modelValue')).toBe('ticket');
    expect([s.form().exists(), s.summary().exists(), s.side().attributes('data-folded')]).toEqual([false, false, undefined]);
  });

  it('choosing Invoice asks who it is for, right below, and opens the group', async () => {
    const s = await setup();
    await click(s.find('sale-checkout-doc-invoice').element);
    expect(s.wrapper.emitted('update:document')).toEqual([['invoice']]);
    expect(s.wrapper.emitted('update:open')).toEqual([[true]]);
    expect([s.form().props('reason'), s.form().props('modelValue')]).toEqual(['invoice', RECIPIENT]);
  });

  it('the recipient typed goes up', async () => {
    const s = await setup({ document: 'invoice', open: true });
    s.form().vm.$emit('update:modelValue', { ...RECIPIENT, taxId: 'B1' });
    expect(s.wrapper.emitted('update:recipient')).toEqual([[{ ...RECIPIENT, taxId: 'B1' }]]);
  });

  it('on a phone an invoice folds into its summary line, which opens and closes it', async () => {
    const s = await setup({ document: 'invoice', open: false });
    expect(s.summary().text()).toBe('Invoice · Bar Pepe SL');
    expect([s.side().attributes('data-folded'), s.summary().attributes('aria-expanded')]).toEqual(['true', 'false']);
    await click(s.summary().element);
    expect([s.side().attributes('data-folded'), s.summary().attributes('aria-expanded')]).toEqual([undefined, 'true']);
    await click(s.summary().element);
    expect(s.side().attributes('data-folded')).toBe('true');
  });

  it('an invoice without a name yet says only «Invoice»', async () => {
    const s = await setup({ document: 'invoice', recipient: { ...RECIPIENT, name: ' ' } });
    expect(s.summary().text()).toBe('Invoice');
  });

  it('over the ticket limit there is no Receipt: the details, with the limit', async () => {
    const s = await setup({ document: 'invoice', overLimit: true, open: true });
    expect(s.wrapper.findComponent(DocumentChooser).exists()).toBe(false);
    expect([s.form().props('reason'), s.form().props('max')]).toEqual(['limit', 300000]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ document: 'invoice' }, 'es');
    expect(s.summary().text()).toBe('Factura · Bar Pepe SL');
  });
});
