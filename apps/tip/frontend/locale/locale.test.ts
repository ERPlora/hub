// The tips app's UI texts: English source + Spanish. This test is their guardrail: same keys and placeholders in both
// languages, nothing empty, and every key a component or a helper of the app uses exists.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('tip', en, es);

describe('tips catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'only' });

  it('say the charge’s words as the WORKBOOK writes them', () => {
    expect(CATALOGUES.ES.get('tip.step.none')).toBe('Sin propina');
    expect(CATALOGUES.ES.get('tip.step.custom')).toBe('Otra cantidad');
    expect(CATALOGUES.ES.get('tip.step.notSaved')).toBe('La venta está cobrada, pero la propina no se ha guardado.');
  });
});
