// The discount sheet (SALE-F14): «Ticket discount» or «Discount on <item>»; a percentage on the keypad
// (the ticket can switch to a fixed amount with the currency button), «Apply −N %» / «Apply −<amount>»
// and «Remove». It hands the discount up; the page picks the door (the manager's above the cap) and a
// refusal is read in the sheet.
import { describe, expect, it, vi } from 'vitest';

import { click, errorFrame, expectWaitsForTheYen, settle } from '../../__tests__/mount-sale';
import { expectWindowSaysMoneyUnreadable } from '../../../../../base/frontend/__tests__/save-waits-for-money';
import { plain } from '../../lib/format';
import { mountDiscountSheet } from './__tests__/discount-sheet';
import DiscountSheet from './DiscountSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

/** How the sheet is mounted: `business: null`, `base.business.get` never answers (its money unknown, hub#921). */
type Options = { business?: null };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en', options: Options = {}) {
  const m = await mountDiscountSheet(props, { locale, ...options });
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
  return { ...m, press, sheet, mode };
}

describe('DiscountSheet: the ticket', () => {
  it('is «Ticket discount», in percent, with «%» and the currency to choose', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-discount-title').text()).toBe('Descuento del tique');
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

describe('DiscountSheet: before the business answers its money (hub#921)', () => {
  it('a fixed amount waits in grey and hands up nothing; once the yen arrives «1500» is 1500', async () => {
    const m = await setup({ amount: 500 }, 'en', { business: null });
    await m.press('1', '5', '0', '0');
    await expectWaitsForTheYen(m, 'pos-discount-apply', () => m.sheet().emitted('apply') ?? []);
    expect(plain(m.find('pos-discount-value').text())).toBe('¥1,500');
    await click(m.find('pos-discount-apply').element);
    expect(m.sheet().emitted('apply')).toEqual([[{ percent: '0', amount: 1500 }]]);
  });

  it('a percentage reads no money: it does not wait for the business', async () => {
    const m = await setup({}, 'en', { business: null });
    await m.press('1', '0');
    await click(m.find('pos-discount-apply').element);
    expect(m.sheet().emitted('apply')).toEqual([[{ percent: '10', amount: 0 }]]);
  });
});

describe('DiscountSheet: a business whose money cannot be read (hub#938)', () => {
  it('a fixed amount says so with «Retry» instead of waiting in grey without a word; once the yen arrives it lights up', async () => {
    const m = await setup({ amount: 500 }, 'en', { business: null });
    await m.press('1', '5', '0', '0');
    await expectWindowSaysMoneyUnreadable(m, 'pos-discount-apply', () => m.sheet().emitted('apply') ?? []);
  });

  it('a percentage reads no money: the failure says nothing there and it still applies', async () => {
    const m = await setup({}, 'en', { business: null });
    m.net.lastStream().push(errorFrame(m.subId('base.business.get'), 'base.hub_busy'));
    await settle();
    await m.press('1', '0');
    expect(m.inDoc('base-money-error')).toBeNull();
    await click(m.find('pos-discount-apply').element);
    expect(m.sheet().emitted('apply')).toEqual([[{ percent: '10', amount: 0 }]]);
  });
});
