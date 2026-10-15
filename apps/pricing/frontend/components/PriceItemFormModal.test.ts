// PRICING-F07 and F08: «New price» picks Product or Service, the article (searched in Inventory or in
// Services), From quantity (1) and Price (typed as a person does); «Add» needs an article and a price.
// A row's Edit opens «Editing price — {name}» with its quantity and price and sends only what changed.
// Refusals stay in the dialog, under their field.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { priceItem } from '../__tests__/fixtures';
import { click, ionValue, mountPricing, settle } from '../__tests__/mount-pricing';
import PriceItemFormModal from './PriceItemFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountPricing(PriceItemFormModal, { props: { open: false, priceListId: 'l1', item: null, ...props }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`pricing-item-form-${name}`) as Control;
  const save = () => m.inDoc('pricing-item-form-submit') as Control;
  const article = () => m.wrapper.findComponent(Combo);
  return { ...m, field, save, article };
}

describe('PriceItemFormModal', () => {
  it('asks for the type, the article, the from quantity and the price, and needs article and price', async () => {
    const s = await setup();
    expect(s.inDoc('pricing-item-form')?.getAttribute('aria-label')).toBe('New price');
    expect(s.field('kind').value).toBe('product');
    expect([s.article().props('label'), s.article().props('placeholder')]).toEqual(['Product', 'Search by name or SKU']);
    expect([s.field('min_quantity').value, s.field('min_quantity').label]).toEqual(['1', 'From quantity']);
    expect(s.save().disabled).toBe(true);
    s.article().vm.$emit('update:modelValue', { id: 'p1', label: 'Shampoo' });
    await settle();
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('price'), '12,50', 'ionInput');
    expect(s.save().disabled).toBe(false);
  });

  it('adds a product price in cents from the quantity typed with a comma', async () => {
    const s = await setup();
    s.answer(201, priceItem());
    s.article().vm.$emit('update:modelValue', { id: 'p1', label: 'Shampoo' });
    await settle();
    await ionValue(s.field('min_quantity'), '0,5', 'ionInput');
    await ionValue(s.field('price'), '12,50', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/pricing/price_items', query: {}, body: { price_list_id: 'l1', product_id: 'p1', min_quantity: '0.5', price: 1250 } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a service is searched in Services and sent as such', async () => {
    const s = await setup();
    s.answer(201, priceItem({ kind: 'service' }));
    await ionValue(s.field('kind'), 'service');
    expect(s.article().props('label')).toBe('Service');
    s.article().vm.$emit('update:modelValue', { id: 's1', label: 'Haircut' });
    await settle();
    await ionValue(s.field('price'), '15', 'ionInput');
    await click(s.save());
    expect(s.sent()[0].body).toEqual({ price_list_id: 'l1', service_id: 's1', min_quantity: '1', price: 1500 });
  });

  it('a quantity already priced is said under its field', async () => {
    const s = await setup();
    const message = 'That article already has a price in this list from that quantity.';
    s.answer(409, { error: { code: 'pricing.price_item_exists', message, fields: { min_quantity: message } } });
    s.article().vm.$emit('update:modelValue', { id: 'p1', label: 'Shampoo' });
    await settle();
    await ionValue(s.field('price'), '12', 'ionInput');
    await click(s.save());
    expect(s.field('min_quantity').errorText).toBe(message);
  });

  it('edits a price sending only what changed', async () => {
    const s = await setup({ item: priceItem({ min_quantity: '10.000', price: 1000 }) });
    expect(s.inDoc('pricing-item-form')?.getAttribute('aria-label')).toBe('Editing price — Shampoo');
    expect(s.inDoc('pricing-item-form-kind')).toBeNull();
    expect([s.field('min_quantity').value, s.field('price').value]).toEqual(['10', '10.00']);
    s.answer(200, priceItem());
    await ionValue(s.field('price'), '9.50', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/price_items/update', query: {}, body: { id: 'i1', price: 950 } }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.inDoc('pricing-item-form')?.getAttribute('aria-label')).toBe('Nuevo precio');
    expect(s.field('min_quantity').label).toBe('Desde la cantidad');
  });
});
