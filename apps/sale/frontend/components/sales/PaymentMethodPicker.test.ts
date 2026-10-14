// The payment-method picker of Sales (the «Payment» filter; «Give it back through» in a refund): a
// read-only outlined field that opens a window with a searchbar and the list. The list is the server's
// (`sale.payment_method.list`, searched there, a short page): never every method loaded at once. A
// method is named as the reader reads it (`display_name`); what is chosen is its stored name (a filter
// compares the sale's stored method) or its id (a refund's destination).
import { describe, expect, it, vi } from 'vitest';

import { click, errorFrame, flush, ionValue, mountSale } from '../../__tests__/mount-sale';
import type { PaymentMethodOut } from '../../operations';
import PaymentMethodPicker from './PaymentMethodPicker.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const method = (id: string, name: string, display: string, over: Partial<PaymentMethodOut> = {}): PaymentMethodOut => ({
  id,
  name,
  display_name: display,
  type: 'other',
  sort_order: 0,
  requires_change: false,
  allowed: true,
  ...over,
});
/** An Ionic property as the element holds it (Vue sets them as properties, not attributes). */
const prop = (el: Element, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const METHODS = { rows: [method('m1', 'Cash', 'Efectivo', { type: 'cash' }), method('m2', 'Card', 'Tarjeta', { type: 'card' }), method('m3', 'Bizum', 'Bizum')], total: 3, limit: 20, offset: 0 };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(PaymentMethodPicker, {
    props: { modelValue: '', valueKey: 'name', label: 'Payment', testid: 'pick', ...props },
    locale,
  });
  const call = await m.live();
  const field = () => m.find('pick');
  const options = () => m.wrapper.findAll('[data-testid="pick-option"]').map((o) => [o.attributes('data-value'), o.text()]);
  async function openIt() {
    await click(field().element);
  }
  return { ...m, call, field, options, openIt };
}

describe('PaymentMethodPicker', () => {
  it('asks the server for a short page of methods, and searches there', async () => {
    const s = await setup();
    expect(s.params('sale.payment_method.list')).toEqual([{ limit: 20 }]);
    await s.openIt();
    await ionValue(s.find('pick-search').element, 'biz', 'ionInput');
    await s.reopen();
    expect(s.params('sale.payment_method.list')).toEqual([{ search: 'biz', limit: 20 }]);
  });

  it('lists the methods by the name the reader reads, with «Any» first when it is a filter', async () => {
    const s = await setup({ anyLabel: 'Any' });
    await s.result('sale.payment_method.list', METHODS);
    await s.openIt();
    expect(s.options()).toEqual([
      ['', 'Any'],
      ['Cash', 'Efectivo'],
      ['Card', 'Tarjeta'],
      ['Bizum', 'Bizum'],
    ]);
  });

  it('a filter chooses the stored name; the field then shows the reader’s name', async () => {
    const s = await setup();
    await s.result('sale.payment_method.list', METHODS);
    await s.openIt();
    await click(s.wrapper.findAll('[data-testid="pick-option"]')[1].element);
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['Card']]);
    await s.wrapper.setProps({ modelValue: 'Card' });
    expect((s.field().element as HTMLElement & { value?: string }).value).toBe('Tarjeta');
  });

  it('a refund’s destination chooses the method’s id', async () => {
    const s = await setup({ valueKey: 'id' });
    await s.result('sale.payment_method.list', METHODS);
    await s.openIt();
    expect(s.options().map(([value]) => value)).toEqual(['m1', 'm2', 'm3']);
    await click(s.wrapper.findAll('[data-testid="pick-option"]')[2].element);
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['m3']]);
  });

  it('says it is loading, that nothing matches, or that the methods could not be loaded', async () => {
    const s = await setup();
    await s.openIt();
    expect(s.find('pick-loading').exists()).toBe(true);
    await s.result('sale.payment_method.list', { rows: [], total: 0, limit: 20, offset: 0 });
    expect(s.find('pick-empty').text()).toBe('No payment method matches your search.');
    s.call.push(errorFrame(s.subId('sale.payment_method.list'), 'sale.boom'));
    await flush();
    expect(s.find('pick-error').text()).toContain('The payment methods could not be loaded.');
  });

  it('is an outlined field in md mode, with its error under it', async () => {
    const s = await setup({ errorText: 'Pick one' });
    const field = s.field();
    expect([prop(field.element, 'fill'), field.attributes('mode') ?? prop(field.element, 'mode'), prop(field.element, 'errorText')]).toEqual(['outline', 'md', 'Pick one']);
    expect(field.classes()).toContain('ion-invalid');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    await s.openIt();
    expect(prop(s.find('pick-search').element, 'placeholder')).toBe('Buscar…');
    expect(s.find('pick-close').attributes('aria-label')).toBe('Cerrar');
    await s.result('sale.payment_method.list', { rows: [], total: 0, limit: 20, offset: 0 });
    expect(s.find('pick-empty').text()).toBe('Ninguna forma de pago coincide con la búsqueda.');
  });
});
