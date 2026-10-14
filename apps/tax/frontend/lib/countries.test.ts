// The countries a tax rule may be set for (TAX-F04): the closed ISO 3166-1 list the server accepts
// (`schemas.COUNTRY_CODES`, from pycountry), named in the reader's language with their code, so the
// form and the filter offer only what the server will take and typing «ES» finds Spain.
import { describe, expect, it } from 'vitest';

import { COUNTRY_CODES, countryChoices, countryLabel, countryOptions } from './countries';

describe('COUNTRY_CODES: the 249 codes the server accepts', () => {
  it('are the 249 officially assigned ISO 3166-1 alpha-2 codes, sorted and unique', () => {
    expect(COUNTRY_CODES).toHaveLength(249);
    expect(new Set(COUNTRY_CODES).size).toBe(249);
    expect([...COUNTRY_CODES].sort()).toEqual([...COUNTRY_CODES]);
    for (const code of COUNTRY_CODES) expect(code).toMatch(/^[A-Z]{2}$/);
  });

  it('hold the ones a business sells from, and none of the unassigned or reserved ones', () => {
    for (const code of ['ES', 'PT', 'FR', 'DE', 'IT', 'GB', 'US', 'MX', 'AD']) expect(COUNTRY_CODES).toContain(code);
    for (const code of ['ZZ', 'EU', 'XK', 'UK', 'EL']) expect(COUNTRY_CODES).not.toContain(code);
  });
});

describe('countryOptions: what the pickers offer', () => {
  it('names every country in the reader’s language and keeps its code, so typing ES finds Spain', () => {
    const es = countryOptions('es');
    expect(es).toHaveLength(249);
    expect(es.find((o) => o.value === 'ES')).toEqual({ value: 'ES', label: 'España (ES)' });
    expect(countryOptions('en').find((o) => o.value === 'ES')).toEqual({ value: 'ES', label: 'Spain (ES)' });
  });

  it('sorts by the name the reader sees, not by the code', () => {
    const labels = countryOptions('en').map((o) => o.label);
    const sorted = [...labels].sort(new Intl.Collator('en').compare);
    expect(labels).toEqual(sorted);
  });

  it('is built once per language: the same array comes back', () => {
    expect(countryOptions('en')).toBe(countryOptions('en'));
    expect(countryOptions('es')).not.toBe(countryOptions('en'));
  });

  it('falls back to the bare code on a language the platform cannot read', () => {
    expect(countryOptions('not a language!').find((o) => o.value === 'ES')?.label).toMatch(/\(ES\)$|^ES$/);
  });
});

describe('countryLabel: one code as the reader reads it', () => {
  it('names a known code with its code, and keeps an unknown one as it came', () => {
    expect(countryLabel('PT', 'en')).toBe('Portugal (PT)');
    expect(countryLabel('PT', 'es')).toBe('Portugal (PT)');
    expect(countryLabel('ZZ', 'en')).toBe('ZZ');
  });
});

describe('countryChoices: some codes (those a business has rules for) as a filter offers them', () => {
  it('names them for the reader, sorts them by that name, once each, and keeps an unknown code', () => {
    expect(countryChoices(['ES', 'PT', 'ES', 'ZZ'], 'en')).toEqual([
      { value: 'PT', label: 'Portugal (PT)' },
      { value: 'ES', label: 'Spain (ES)' },
      { value: 'ZZ', label: 'ZZ' },
    ]);
    expect(countryChoices(['PT', 'ES'], 'es').map((o) => o.label)).toEqual(['España (ES)', 'Portugal (PT)']);
  });
});
