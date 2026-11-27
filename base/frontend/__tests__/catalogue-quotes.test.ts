// English quotes a name with English quotation marks (“…”): the angle quotes «…» are Spanish's, and only the Spanish
// catalogues keep them. Read on every English catalogue of the Hub's SPA, the platform's and each app's.
import { basename, join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import moneyField from '../../../packages/ui/src/components/MoneyInput/locales/en.json';
import { flattened, HUB, hubCatalogues } from './hub-catalogues';

const ENGLISH = hubCatalogues().filter((file) => basename(file) === 'en.json');

/** The money field's own words (`MoneyInput`, in @erplora/ui). The amount filters repeat them word for word, so every
 *  list says it as the money field does (amount-filter.test.ts holds them equal): they follow its catalogue. */
const MONEY_FIELD = new Set<string>(Object.values(moneyField.moneyInput));

const angleQuoted = ENGLISH.flatMap((file) => [...flattened(file)].filter(([, message]) => /[«»]/.test(message)));

describe('every English catalogue of the Hub', () => {
  it('is read: the platform’s and every app’s', () => {
    const files = ENGLISH.map((file) => relative(HUB, file));
    expect(files).toContain(join('base', 'frontend', 'locale', 'en.json'));
    expect(files).toContain(join('apps', 'sale', 'frontend', 'locale', 'en.json'));
    expect(files.length).toBeGreaterThan(25);
  });

  it('quotes with “…”, never the Spanish «…»', () => {
    const found = angleQuoted.filter(([, message]) => !MONEY_FIELD.has(message)).map(([where, message]) => `${where}: ${message}`);
    expect(found, found.join('\n')).toEqual([]);
  });

  it('leaves to the money field only the amount filters’ words, which are its own', () => {
    const borrowed = angleQuoted.filter(([, message]) => MONEY_FIELD.has(message)).map(([where]) => where);
    for (const where of borrowed) expect(where).toMatch(/^base\/frontend\/locale\/en\.json › base\.money\.filter\./);
  });
});
