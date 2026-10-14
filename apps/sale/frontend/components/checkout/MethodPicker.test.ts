// The payment methods of the charge sheet (SALE-F02, F03): big two-up buttons with the method's icon and
// its name in the reader's language, the chosen one pressed; cash over the legal limit stays on screen,
// visibly unavailable but tappable (`aria-disabled`, never `disabled`), so the tap is answered.
import { HubIcon } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import type { PaymentMethodOut } from '../../operations';
import MethodPicker from './MethodPicker.vue';

const method = (id: string, type: PaymentMethodOut['type'], display_name: string): PaymentMethodOut => ({
  id,
  name: id,
  display_name,
  type,
  sort_order: 0,
  requires_change: type === 'cash',
  allowed: true,
});
const METHODS = [method('m-cash', 'cash', 'Efectivo'), method('m-card', 'card', 'Tarjeta'), method('m-bizum', 'other', 'Bizum')];

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(MethodPicker, { props: { methods: METHODS, selectedId: 'm-cash', cashOff: false, ...props }, locale });
  const button = (id: string) => m.find(`sale-checkout-method-${id}`);
  return { ...m, button };
}

describe('MethodPicker', () => {
  it('paints a button per method with its icon and name, in a group named «Payment method»', async () => {
    const s = await setup();
    expect(s.find('sale-checkout-methods').attributes()).toMatchObject({ role: 'group', 'aria-label': 'Payment method' });
    expect(['m-cash', 'm-card', 'm-bizum'].map((id) => s.button(id).text())).toEqual(['Efectivo', 'Tarjeta', 'Bizum']);
    expect(s.wrapper.findAllComponents(HubIcon).map((i) => i.props('name'))).toEqual([
      'ion:cash-outline',
      'ion:card-outline',
      'ion:phone-portrait-outline',
    ]);
  });

  it('marks the chosen method as pressed', async () => {
    const s = await setup({ selectedId: 'm-card' });
    expect(['m-cash', 'm-card', 'm-bizum'].map((id) => s.button(id).attributes('aria-pressed'))).toEqual(['false', 'true', 'false']);
  });

  it('sends the method tapped', async () => {
    const s = await setup();
    await click(s.button('m-card').element);
    expect(s.wrapper.emitted('pick')).toEqual([[METHODS[1]]]);
  });

  it('over the cash limit, cash is unavailable with its reason and still answers the tap', async () => {
    const s = await setup({ cashOff: true, selectedId: 'm-card' });
    expect(s.button('m-cash').attributes()).toMatchObject({ 'aria-disabled': 'true', title: 'Not allowed for this amount' });
    expect(s.button('m-cash').attributes('disabled')).toBeUndefined();
    expect(s.button('m-card').attributes('aria-disabled')).toBeUndefined();
    await click(s.button('m-cash').element);
    expect(s.wrapper.emitted('pick')).toEqual([[METHODS[0]]]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ cashOff: true }, 'es');
    expect(s.find('sale-checkout-methods').attributes('aria-label')).toBe('Forma de pago');
    expect(s.button('m-cash').attributes('title')).toBe('No permitido para este importe');
  });
});
