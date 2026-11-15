// The website editor's UI texts: English source + Spanish, kept by hand next to the pages until Django's `djangojs`
// catalogues are exported to JSON. This test is their guardrail: same keys and placeholders in both languages, nothing
// empty, no vue-i18n syntax by accident, and every key a page, a component or a helper uses exists.
import { describe, expect, it } from 'vitest';

import {
  appCatalogues,
  appSources,
  expectInCatalogue,
  expectSamePlaceholders,
  itChecksAppCatalogues,
  literalKeys,
  usedKeys,
} from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('website', en, es);
const { EN, ES } = CATALOGUES;

describe('website catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'own', coverage: 'own' });

  it('keep the same placeholders in both languages and no other vue-i18n syntax', () => {
    expectSamePlaceholders(CATALOGUES, { pluralForms: false });
    for (const [key, message] of [...EN, ...ES]) expect(message, key).not.toMatch(/[@|$]/);
  });

  it('cover every key the pages, components and helpers use', () => {
    const files = appSources(CATALOGUES.frontend, { skip: ['locale'], declarations: true });
    expect(files.length).toBeGreaterThan(0);
    const keys = usedKeys(files, literalKeys('website'));
    expectInCatalogue(EN, keys);
    expect(keys.length).toBeGreaterThan(20);
  });
});
