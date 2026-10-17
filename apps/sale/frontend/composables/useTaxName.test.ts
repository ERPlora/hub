// `useTaxName()`: the short name of the tax the business's sales are declared with — its territory's, as
// Taxes → Settings keeps it (TAX-F11): «IGIC» in the Canary Islands, «IPSI» in Ceuta and Melilla, «VAT»
// («IVA» in Spanish) anywhere else. Read live (`sale.sale.tax_kind`): a change of territory renames every
// screen. Until it is read, or if it cannot be, the national VAT, the server's own default.
import type { ComputedRef } from 'vue';
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountComposable } from '../__tests__/mount-sale';
import { useTaxName } from './useTaxName';

async function setup(locale: 'en' | 'es' = 'en') {
  let name: ComputedRef<string> | undefined;
  const m = await mountComposable(() => {
    name = useTaxName();
  }, { locale });
  const call = await m.live();
  return { ...m, call, name: () => name!.value };
}

describe('useTaxName', () => {
  it('reads the tax of the business’s territory, live', async () => {
    const s = await setup();
    expect(s.params('sale.sale.tax_kind')).toEqual([{}]);
  });

  it('is the national VAT until the territory is read', async () => {
    expect((await setup()).name()).toBe('VAT');
    expect((await setup('es')).name()).toBe('IVA');
  });

  it.each([
    ['vat', 'en', 'VAT'],
    ['vat', 'es', 'IVA'],
    ['igic', 'en', 'IGIC'],
    ['igic', 'es', 'IGIC'],
    ['ipsi', 'en', 'IPSI'],
    ['ipsi', 'es', 'IPSI'],
  ] as const)('a territory of %s is named «%s» → %s', async (tax, locale, expected) => {
    const s = await setup(locale);
    await s.result('sale.sale.tax_kind', { tax });
    expect(s.name()).toBe(expected);
  });

  it('follows a change of territory', async () => {
    const s = await setup();
    await s.result('sale.sale.tax_kind', { tax: 'igic' });
    expect(s.name()).toBe('IGIC');
    await s.result('sale.sale.tax_kind', { tax: 'vat' }, {}, 2);
    expect(s.name()).toBe('VAT');
  });

  it('a failed read keeps the national VAT', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId('sale.sale.tax_kind'), 'sale.boom'));
    await flush();
    expect(s.name()).toBe('VAT');
  });

  it('a failed re-read keeps the territory already read', async () => {
    const s = await setup();
    await s.result('sale.sale.tax_kind', { tax: 'igic' });
    s.call.push(errorFrame(s.subId('sale.sale.tax_kind'), 'sale.boom'));
    await flush();
    expect(s.name()).toBe('IGIC');
  });
});
