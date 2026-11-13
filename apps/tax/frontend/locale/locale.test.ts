// The tax app's UI texts: English source + Spanish, kept by hand next to the pages until
// Django's `djangojs` catalogues are exported to JSON (as the demo's). This test is their guardrail:
// same keys and placeholders in both languages, nothing empty, every key a page, a component or a
// helper of the app uses exists, and the texts the old screens showed are kept word for word.
import { describe, expect, it } from 'vitest';

import { appCatalogues, itChecksAppCatalogues } from '../../../../base/frontend/__tests__/app-catalogues';
import en from './en.json';
import es from './es.json';

const CATALOGUES = appCatalogues('tax', en, es);
const { EN, ES } = CATALOGUES;

describe('tax catalogues (en source + es)', () => {
  itChecksAppCatalogues(CATALOGUES, { placeholders: 'and plural forms' });

  it('name every family and every qualification the server knows', () => {
    for (const type of ['vat', 'igic', 'ipsi', 'surcharge', 'sales_tax', 'withholding', 'excise', 'import_duty']) {
      expect(EN.has(`tax.types.${type}`), type).toBe(true);
    }
    for (const cls of ['subject', 'subject_reverse', 'exempt', 'not_subject', 'not_subject_location']) {
      expect(EN.has(`tax.classes.${cls}`), cls).toBe(true);
    }
  });

  it('keep the old screens’ words (the WORKBOOK’s screens): read-only notice, empty states, deactivation', () => {
    expect(ES.get('tax.readOnly')).toBe('Puedes consultar las reglas fiscales pero no modificarlas.');
    expect(ES.get('tax.categories.empty')).toBe('Sin categorías fiscales.');
    expect(ES.get('tax.rules.empty')).toBe('Sin reglas fiscales.');
    expect(ES.get('tax.aliases.empty')).toBe('Sin alias de categorías.');
    expect(ES.get('tax.rules.deactivate.title')).toBe('Desactivar regla fiscal');
    expect(ES.get('tax.rules.deactivate.confirm')).toBe('Desactivar regla');
    expect(ES.get('tax.rules.end.submit')).toBe('Guardar fecha de fin');
    expect(ES.get('tax.rules.form.rateNoTax')).toBe('Esta operación no lleva impuesto, así que su tipo es 0 %.');
  });
});
