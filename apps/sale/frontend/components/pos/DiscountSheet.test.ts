// The discount sheet (SALE-F14): «Ticket discount» or «Discount on <item>»; a percentage on the keypad
// (the ticket can switch to a fixed amount with the currency button), «Apply −N %» / «Apply −<amount>»
// and «Remove». It hands the discount up; the page picks the door (the manager's above the cap) and a
// refusal is read in the sheet.
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import DiscountSheet from './DiscountSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const m = await mountSale(
    {
      setup: () => () =>
        h(DiscountSheet, {
          open: open.value,
          'onUpdate:open': (v: boolean) => (open.value = v),
          name: null,
          amount: 0,
          pending: false,
          error: null,
          ...props,
        }),
    },
    { locale },
  );
  await m.live();
  await settle();
  const press = async (...keys: string[]) => {
    for (const key of keys) await click(m.find(`pos-key-${key}`).element);
  };
  const sheet = () => m.wrapper.findComponent(DiscountSheet);
  const mode = async (value: string) => {
    m.find('pos-discount-mode').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await settle();
  };
  return { ...m, open, press, sheet, mode };
}

describe('DiscountSheet: the ticket', () => {
  it('is «Ticket discount», in percent, with «%» and the currency to choose', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-discount-title').text()).toBe('Descuento del ticket');
    const options = m.find('pos-discount-mode').findAll('ion-segment-button').map((b) => (b.element as HTMLElement & { value?: string }).value);
    expect(options).toEqual(['percent', 'amount']);
    expect(m.find('pos-discount-mode').findAll('ion-label').map((l) => l.element.innerHTML.trim())).toEqual(['%', '€']);
    await m.press('1', '0');
    expect(plain(m.find('pos-discount-value').text())).toBe('10 %');
    expect(plain(m.find('pos-discount-apply').text())).toBe('Aplicar −10 %');
  });

  it('applies a percentage (and no fixed amount)', async () => {
    const m = await setup();
    await m.press('1', '2', 'dot', '5');
    await click(m.find('pos-discount-apply').element);
    expect(m.sheet().emitted('apply')).toEqual([[{ percent: '12.5', amount: 0 }]]);
  });

  it('never more than 100 %', async () => {
    const m = await setup();
    await m.press('1', '0', '0', '5');
    expect(plain(m.find('pos-discount-value').text())).toBe('100%');
  });

  it('switches to a fixed amount, which starts empty, and applies it in cents', async () => {
    const m = await setup({}, 'es');
    await m.press('5');
    await m.mode('amount');
    expect(plain(m.find('pos-discount-value').text())).toBe('0,00 €');
    await m.press('5');
    expect(plain(m.find('pos-discount-apply').text())).toBe('Aplicar −5,00 €');
    await click(m.find('pos-discount-apply').element);
    expect(m.sheet().emitted('apply')).toEqual([[{ percent: '0', amount: 500 }]]);
  });

  it('a check with only a fixed amount opens on the amount', async () => {
    const m = await setup({ amount: 300 });
    expect((m.find('pos-discount-mode').element as HTMLElement & { value?: string }).value).toBe('amount');
  });

  it('«Remove» takes both off; nothing typed, nothing to apply', async () => {
    const m = await setup();
    expect((m.find('pos-discount-apply').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    await click(m.find('pos-discount-remove').element);
    expect(m.sheet().emitted('apply')).toEqual([[{ percent: '0', amount: 0 }]]);
  });
});

describe('DiscountSheet: a line', () => {
  it('is «Discount on <item>», percent only', async () => {
    const m = await setup({ name: 'Steak' }, 'es');
    expect(m.find('pos-discount-title').text()).toBe('Descuento en Steak');
    expect(m.find('pos-discount-mode').exists()).toBe(false);
    await m.press('2', '0');
    await click(m.find('pos-discount-apply').element);
    expect(m.sheet().emitted('apply')).toEqual([[{ percent: '20', amount: 0 }]]);
  });

  it('a refusal is read in the sheet', async () => {
    const m = await setup({ name: 'Steak', error: 'That discount is over what this business allows without the manager.' });
    expect(m.find('pos-discount-error').text()).toBe('That discount is over what this business allows without the manager.');
  });
});
