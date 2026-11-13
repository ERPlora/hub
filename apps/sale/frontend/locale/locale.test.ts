// The sale app's UI texts: English source + Spanish, kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON (as the demo's). This test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page, a component or a
// helper of the app uses exists, and the texts the old screens showed are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('sale', en, es);
const { ES } = CATALOGUES;

describe('sale catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('keep the old screens’ words (WORKBOOK «Pantallas»)', () => {
    expect(ES.get('sale.title')).toBe('Ventas / TPV');
    expect(ES.get('sale.tabs.pos')).toBe('Vender');
    expect(ES.get('sale.tabs.sales')).toBe('Ventas');
    expect(ES.get('sale.tabs.quickNotes')).toBe('Notas rápidas');
    // «Departamentos» does not fit a fifth of a phone's tabbar.
    expect(ES.get('sale.tabs.departments')).toBe('Secciones');
    expect(ES.get('sale.tabs.settings')).toBe('Ajustes');
  });
});

