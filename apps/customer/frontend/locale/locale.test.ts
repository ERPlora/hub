// The customer app's UI texts: English source + Spanish, kept by hand next to the pages. This test is
// their guardrail: same keys and placeholders in both languages, nothing empty, every key a page, a
// component or a helper names exists, and no vue-i18n special character left unescaped.
import { describe, expect, it } from 'vitest';

import {
  appCatalogues,
  appSources,
  expectInCatalogue,
  itChecksAppCatalogues,
  literalKeys,
  usedKeys,
} from '../../../../base/frontend/__tests__/app-catalogues';
import OPERATIONS from '../../../../frontend/generated/operations.json';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('customer', en, es);
const { EN, ES } = CATALOGUES;

describe('customer catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms', coverage: 'own' });

  it('use no vue-i18n linked-message sign (@) nor a stray brace: they would break the message', () => {
    for (const [key, message] of [...EN, ...ES]) {
      expect(message, key).not.toMatch(/@|\$/);
      expect(message.replace(/\{\w+\}/g, ''), key).not.toMatch(/[{}]/);
    }
  });

  it('cover every key the pages, components and helpers use', () => {
    const files = appSources(CATALOGUES.frontend);
    expect(files.length).toBeGreaterThan(0);
    const keys = usedKeys(files, literalKeys('customer'));
    expectInCatalogue(EN, keys);
    expect(keys.length).toBeGreaterThan(0);
  });

  it('cover every key held in a literal too (tables of labels), operation names aside', () => {
    const operations = new Set(Object.keys(OPERATIONS));
    const keys = usedKeys(appSources(CATALOGUES.frontend), /'(customer\.[a-z][\w]*\.[\w.]+)'/g);
    expectInCatalogue(EN, keys.filter(({ key }) => !operations.has(key) && !key.endsWith('.')));
  });
});
