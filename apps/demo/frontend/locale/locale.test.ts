// The demo's UI texts: English source + Spanish, kept by hand next to the pages. This test is their
// guardrail: same keys and placeholders in both languages, nothing empty, every key a page uses exists.
import { describe, expect, it } from 'vitest';

import { appCatalogues, appSources, expectInCatalogue, itChecksAppCatalogues, usedKeys } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('demo', en, es);
const { EN } = CATALOGUES;

describe('demo catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms', coverage: 'own' });

  it('cover every key the demo pages and components use', () => {
    const files = appSources(CATALOGUES.frontend, { skip: [], extensions: ['.vue'] });
    expect(files.length).toBeGreaterThan(0);
    expectInCatalogue(EN, usedKeys(files, /\$t\(\s*'([^']+)'/g));
  });
});
