// The «IRPF withholding» of a manual invoice (INVOICE-F03): none to begin with, or one of the closed list. Only where the
// tax exists: a business abroad is not asked.
import { describe, expect, it } from 'vitest';

import { business, ionValue, mountInvoice, POLISH } from '../__tests__/mount-invoice';
import { plain } from '../lib/format';
import WithholdingSelect from './WithholdingSelect.vue';

type Select = HTMLElement & { value: unknown; label: string; errorText?: string };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(WithholdingSelect, { props: { modelValue: null, ...props }, locale });
  await m.live();
  const select = () => m.find('invoice-create-withholding').element as Select;
  const options = () => [...select().querySelectorAll('ion-select-option')].map((o) => [(o as unknown as Select).value, plain(o.textContent?.trim() ?? '')]);
  const chosen = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
  return { ...m, select, options, chosen };
}

describe('WithholdingSelect', () => {
  it('offers none and the rates of the list', async () => {
    const s = await setup();
    expect([s.select().label, s.select().value]).toEqual(['IRPF withholding', 0]);
    expect(s.options()).toEqual([[0, 'No withholding'], [15, '15%'], [7, '7%'], [1, '1%'], [19, '19%']]);
  });

  it('gives the rate chosen, and none again', async () => {
    const s = await setup();
    await ionValue(s.select(), 15);
    await ionValue(s.select(), 0);
    expect(s.chosen()).toEqual([15, null]);
  });

  it('shows the rate it has', async () => {
    expect((await setup({ modelValue: 19 })).select().value).toBe(19);
  });

  it('says a refusal under it', async () => {
    const s = await setup({ errorText: 'A ticket carries no IRPF withholding.' });
    expect(s.select().errorText).toBe('A ticket carries no IRPF withholding.');
    expect([...s.select().classList]).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    const fine = await setup();
    expect([...fine.select().classList]).not.toContain('ion-invalid');
  });

  it('is asked in Spain, and before the business answers', async () => {
    const s = await setup();
    expect(s.find('invoice-create-withholding').exists()).toBe(true);
    await s.result('base.business.get', business());
    expect(s.find('invoice-create-withholding').exists()).toBe(true);
  });

  it('is asked in a business that keeps no country: it is read as one in Spain', async () => {
    const s = await setup();
    await s.result('base.business.get', business({ country: '' }));
    expect(s.find('invoice-create-withholding').exists()).toBe(true);
  });

  it('is not asked in a business abroad: the tax is Spanish', async () => {
    const s = await setup();
    await s.result('base.business.get', business(POLISH));
    expect(s.find('invoice-create-withholding').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.select().label).toBe('Retención de IRPF');
    expect(s.options().slice(0, 2)).toEqual([[0, 'Sin retención'], [15, '15 %']]);
  });
});
