// The tax of the business's territory as every app names it (TAX-F11), read from the one place that keeps it:
// `tax.settings.get` (Taxes → Settings), live. `useTaxKind()` is its family (`vat`, `igic` in the Canary
// Islands, `ipsi` in Ceuta and Melilla), unknown until read; `useTaxName()` its short name in the reader's
// language («VAT»/«IVA», «IGIC», «IPSI»), the national VAT until read or when it cannot be; `taxNameKey`
// names any family the same way (a figure of Sales names the tax its sales declared).
import type { ComputedRef } from 'vue';
import { defineComponent, h } from 'vue';
import { describe, expect, it } from 'vitest';

import { errorFrame, flush, mountTax } from '../__tests__/mount-tax';
import en from '../locale/en.json';
import es from '../locale/es.json';
import type { TaxSettingsOut, TerritoryTaxKind } from '../operations';
import { taxNameKey, useTaxKind, useTaxName } from './useTaxName';

const SETTINGS = 'tax.settings.get';

function settings(tax_kind: TerritoryTaxKind, region_code: string | null = null): TaxSettingsOut {
  return { country_code: 'ES', region_code, regions: ['ES-CN', 'ES-CE', 'ES-ML'], tax_kind, updated_at: null };
}

async function setup(locale: 'en' | 'es' = 'en') {
  let name: ComputedRef<string> | undefined;
  let kind: ComputedRef<TerritoryTaxKind | undefined> | undefined;
  const Host = defineComponent({
    setup() {
      name = useTaxName();
      kind = useTaxKind();
      return () => h('div');
    },
  });
  const m = await mountTax(Host, { locale });
  const call = await m.live();
  return { ...m, call, name: () => name!.value, kind: () => kind!.value };
}

describe('useTaxName / useTaxKind', () => {
  it('read the business’s tax settings, live, with one subscription for both', async () => {
    const s = await setup();
    expect(s.params(SETTINGS)).toEqual([{}]);
  });

  it('are the national VAT by name and unknown by family until the settings are read', async () => {
    const s = await setup();
    expect([s.name(), s.kind()]).toEqual(['VAT', undefined]);
    expect((await setup('es')).name()).toBe('IVA');
  });

  it.each([
    ['vat', 'en', 'VAT'],
    ['vat', 'es', 'IVA'],
    ['igic', 'en', 'IGIC'],
    ['igic', 'es', 'IGIC'],
    ['ipsi', 'en', 'IPSI'],
    ['ipsi', 'es', 'IPSI'],
  ] as const)('a territory of %s in %s is named «%s»', async (tax, locale, expected) => {
    const s = await setup(locale);
    await s.result(SETTINGS, settings(tax));
    expect([s.kind(), s.name()]).toEqual([tax, expected]);
  });

  it('follow a change of territory', async () => {
    const s = await setup();
    await s.result(SETTINGS, settings('igic', 'ES-CN'));
    expect([s.kind(), s.name()]).toEqual(['igic', 'IGIC']);
    await s.result(SETTINGS, settings('vat'), {}, 2);
    expect([s.kind(), s.name()]).toEqual(['vat', 'VAT']);
  });

  it('a failed read keeps the national VAT and leaves the family unknown', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(SETTINGS), 'tax.boom'));
    await flush();
    expect([s.name(), s.kind()]).toEqual(['VAT', undefined]);
  });

  it('a failed re-read keeps the territory already read', async () => {
    const s = await setup();
    await s.result(SETTINGS, settings('ipsi', 'ES-ML'));
    s.call.push(errorFrame(s.subId(SETTINGS), 'tax.boom'));
    await flush();
    expect([s.kind(), s.name()]).toEqual(['ipsi', 'IPSI']);
  });
});

describe('taxNameKey', () => {
  it.each([
    ['vat', 'VAT', 'IVA'],
    ['igic', 'IGIC', 'IGIC'],
    ['ipsi', 'IPSI', 'IPSI'],
  ] as const)('names %s «%s» in English and «%s» in Spanish', (kind, english, spanish) => {
    const lookup = (catalogue: unknown, key: string) =>
      key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], catalogue);
    expect(lookup(en, taxNameKey(kind))).toBe(english);
    expect(lookup(es, taxNameKey(kind))).toBe(spanish);
  });
});
