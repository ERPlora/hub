// base's UI texts (the Home and its pieces of the chrome): English source + Spanish. They are kept by hand next to the
// pages, since Django's `djangojs` catalogues are not exported to JSON; this test is their guardrail:
// same keys and placeholders in both languages, nothing empty, «tique» and never «ticket», every key a page uses exists.
import { describe, expect, it } from 'vitest';

import { appCatalogues, appSources, expectInCatalogue, itChecksAppCatalogues, literalKeys, usedKeys } from '../__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('base', en, es);
const { EN } = CATALOGUES;

describe('base catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms', coverage: 'own' });

  it("cover every key base's pages and components use", () => {
    const files = appSources(CATALOGUES.frontend, { skip: [], declarations: true });
    expect(files.length).toBeGreaterThan(0);
    expectInCatalogue(EN, usedKeys(files, literalKeys('base')));
  });
});
