// The inventory's UI texts: English source + Spanish. Kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON; this test is their guardrail: same keys and
// placeholders in both languages, nothing empty, and every key a page, component or composable uses
// exists (`$t('…')` in templates, `t('…')` in scripts).
import { readFileSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import {
  appCatalogues,
  appSources,
  expectInCatalogue,
  itChecksAppCatalogues,
  literalKeys,
  usedKeys,
} from '../../../../base/frontend/__tests__/app-catalogues';
import { pluralsInParentheses } from '../../../../base/frontend/__tests__/catalogue-plurals';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('inventory', en, es);
const { EN, ES } = CATALOGUES;

describe('inventory catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms', coverage: 'own' });

  it('says a count in the singular or the plural, never «(s)»', () => {
    expect(pluralsInParentheses(EN, ES)).toEqual([]);
  });

  it('hold no key that nothing uses (each one is written out whole somewhere in the sources)', () => {
    const sources = appSources(CATALOGUES.frontend).map((file) => readFileSync(file, 'utf8')).join('\n');
    const unused = [...EN.keys()].filter((key) => !sources.includes(`'${key}'`) && !sources.includes(`'${key}`));
    expect(unused).toEqual([]);
  });

  it('cover every key the pages, components and composables use', () => {
    const files = appSources(CATALOGUES.frontend);
    expect(files.length).toBeGreaterThan(0);
    expectInCatalogue(EN, usedKeys(files, literalKeys('inventory')));
  });
});
