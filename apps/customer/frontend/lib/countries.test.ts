// Countries of the customer card (CUSTOMER-F01): the card stores the ISO 3166 two-letter code and a
// person picks the country by its name in their language. The same reader turns what a CSV holds
// («España», «France», «fr») into the code before the import (CUSTOMER-F08), as the product did.
import { describe, expect, it } from 'vitest';

import ISO_CODES from './countries.json';
import { countryCode, countryName, countryOptions } from './countries';

describe('countryOptions', () => {
  it('lists the countries by name in the page language, Spain first, each value its ISO code', () => {
    const es = countryOptions('es');
    expect(es[0]).toEqual({ value: 'ES', label: 'España' });
    expect(es.find((o) => o.value === 'FR')?.label).toBe('Francia');
    const en = countryOptions('en');
    expect(en[0]).toEqual({ value: 'ES', label: 'Spain' });
    expect(en.find((o) => o.value === 'GB')?.label).toBe('United Kingdom');
  });

  it('offers exactly the countries the server accepts (countries.json, generated from pycountry)', () => {
    expect(countryOptions('en').map((o) => o.value).sort()).toEqual([...ISO_CODES].sort());
    for (const code of ['XK', 'AC', 'CP', 'DG', 'TA']) expect(countryOptions('es').some((o) => o.value === code), code).toBe(false);
    expect(countryCode('XK')).toBe('');
  });

  it('holds real countries only, once each: no groupings (EU, UN), no retired codes, no Spanish regions', () => {
    const values = countryOptions('en').map((o) => o.value);
    expect(new Set(values).size).toBe(values.length);
    expect(values.length).toBe(249);
    for (const code of ['EU', 'UN', 'ZZ', 'FX', 'UK', 'IC', 'EA']) expect(values, code).not.toContain(code);
    for (const value of values) expect(value).toMatch(/^[A-Z]{2}$/);
  });

  it('after Spain, sorted by name for that language', () => {
    const labels = countryOptions('es').slice(1).map((o) => o.label);
    expect(labels).toEqual([...labels].sort(new Intl.Collator('es').compare));
  });
});

describe('countryName', () => {
  it('names a stored code in the page language; empty stays empty; an unknown code is shown as stored', () => {
    expect(countryName('FR', 'es')).toBe('Francia');
    expect(countryName('FR', 'en')).toBe('France');
    expect(countryName('', 'es')).toBe('');
    expect(countryName('XQ', 'es')).toBe('XQ');
  });
});

describe('countryCode', () => {
  it('reads a code or a name in English, Spanish or the page language, ignoring case and accents', () => {
    expect(countryCode('fr')).toBe('FR');
    expect(countryCode('España')).toBe('ES');
    expect(countryCode('espana')).toBe('ES');
    expect(countryCode('  United Kingdom ')).toBe('GB');
    expect(countryCode('Alemania')).toBe('DE');
  });

  it('a Spanish region is Spain', () => {
    expect(countryCode('IC')).toBe('ES');
  });

  it('gives nothing for what names no country', () => {
    expect(countryCode('')).toBe('');
    expect(countryCode('Atlantis')).toBe('');
    expect(countryCode('ZZ')).toBe('');
  });
});
