// The amount of a service without a fixed price (SALE-F38, SERVICE-F03): «Amount of <service>», its price
// as the suggestion (one tap types it), the keypad, and «Add <amount>», which waits for an amount. The
// server keeps it within the service's minimum and maximum: its refusal is read over the button.
import { describe, expect, it, vi } from 'vitest';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { service } from './__tests__/fixtures';
import ServicePriceSheet from './ServicePriceSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const COLOUR = service({ id: 'sv2', name: 'Color', pricing_type: 'from', price: 6500, min_price: 4000, max_price: 9000 });

async function setup(props: Record<string, unknown> = {}) {
  const m = await mountSale(ServicePriceSheet, {
    props: { open: true, service: COLOUR, pending: false, error: null, ...props },
    locale: 'es',
  });
  await m.live();
  await settle();
  return m;
}

describe('ServicePriceSheet', () => {
  it('opens blank with the service’s name and its price as the suggestion', async () => {
    const s = await setup();
    expect(s.inDoc('pos-service-price-title')?.textContent).toContain('Importe de Color');
    expect(plain(s.inDoc('pos-service-price-amount')?.textContent ?? '')).toBe('0,00 €');
    expect(plain(s.inDoc('pos-service-price-suggest')?.textContent ?? '')).toBe('Usar 65,00 €');
    expect((s.inDoc('pos-service-price-add') as HTMLButtonElement & { disabled: boolean }).disabled).toBe(true);
  });

  it('one tap on the suggestion types it and «Add» hands it up in cents', async () => {
    const s = await setup();
    await click(s.inDoc('pos-service-price-suggest'));
    expect(plain(s.inDoc('pos-service-price-amount')?.textContent ?? '')).toBe('65,00 €');
    await click(s.inDoc('pos-service-price-add'));
    expect(s.wrapper.emitted('add')).toEqual([[6500]]);
  });

  it('the keypad types another amount', async () => {
    const s = await setup();
    for (const key of ['7', '0']) await click(s.inDoc(`pos-key-${key}`));
    expect(plain(s.inDoc('pos-service-price-amount')?.textContent ?? '')).toBe('70,00 €');
  });

  it('reads the server’s refusal over the button', async () => {
    const s = await setup({ error: 'Ese importe está fuera de lo que admite el servicio (40.00 € – 90.00 €).' });
    expect(s.inDoc('pos-service-price-error')?.textContent).toContain('fuera de lo que admite');
  });
});
