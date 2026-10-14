// What the tax screens read off a rule or a category (TAX-F03–F06): the families and classes they
// offer, which classes charge no tax, and how a rule's category and card title are painted. The
// server decides and validates (the roots of a component too: `tax.rule.parent_candidates`).
import { describe, expect, it } from 'vitest';

import type { RuleOut } from '../operations';
import {
  categoryDisplayName,
  categoryOptionLabel,
  chargesNoTax,
  OPERATION_CLASSES,
  ruleCardTitle,
  ruleCategoryText,
  TAX_TYPES,
} from './rules';

const rule = (over: Partial<RuleOut> = {}): RuleOut => ({
  id: 'r1',
  country_code: 'ES',
  region_code: null,
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restauración — comida',
  rate_pct: '10.00',
  tax_type: 'vat',
  operation_class: 'subject',
  exempt_reason: null,
  regime_key: null,
  parent_id: null,
  component_label: null,
  valid_from: '2012-09-01',
  valid_to: null,
  is_active: true,
  updated_at: '2026-10-13T10:00:00Z',
  ...over,
});

describe('the families and classes a rule may have (schemas.py)', () => {
  it('offers the eight tax families, VAT first, IGIC and IPSI among them', () => {
    expect(TAX_TYPES).toEqual(['vat', 'igic', 'ipsi', 'surcharge', 'sales_tax', 'withholding', 'excise', 'import_duty']);
  });

  it('offers the five fiscal qualifications, subject first', () => {
    expect(OPERATION_CLASSES).toEqual(['subject', 'subject_reverse', 'exempt', 'not_subject', 'not_subject_location']);
  });

  it('every class but subject charges no tax (its rate is 0 %)', () => {
    expect(chargesNoTax('subject')).toBe(false);
    for (const c of ['subject_reverse', 'exempt', 'not_subject', 'not_subject_location'] as const) expect(chargesNoTax(c)).toBe(true);
    expect(chargesNoTax(null)).toBe(false);
  });
});

describe('how a rule is painted', () => {
  it('a root rule shows its category key; a component, «↳» and its label, right under its root', () => {
    expect(ruleCategoryText(rule())).toBe('restaurant.food');
    expect(ruleCategoryText(rule({ parent_id: 'root', component_label: 'Recargo de equivalencia' }))).toBe('↳ Recargo de equivalencia');
    expect(ruleCategoryText(rule({ parent_id: 'root', component_label: null }))).toBe('↳ restaurant.food');
  });

  it('a card is titled with the category a person reads; a component, with its root category and its label', () => {
    expect(ruleCardTitle(rule())).toBe('Restauración — comida');
    expect(ruleCardTitle(rule({ parent_id: 'root', component_label: 'Recargo' }))).toBe('↳ Restauración — comida · Recargo');
    expect(ruleCardTitle(rule({ tax_category_name: '' }))).toBe('restaurant.food');
  });
});

describe('how a category is named', () => {
  it('the name the server resolved for the reader, else the stored name, else the key: never blank', () => {
    expect(categoryDisplayName({ key: 'k', name: 'Stored', display_name: 'Shown' })).toBe('Shown');
    expect(categoryDisplayName({ key: 'k', name: 'Stored', display_name: ' ' })).toBe('Stored');
    expect(categoryDisplayName({ key: 'k', name: '', display_name: '' })).toBe('k');
  });

  it('an option of a picker carries its key too', () => {
    expect(categoryOptionLabel({ key: 'restaurant.food', name: 'Restaurant — food', display_name: 'Restauración — comida' })).toBe(
      'Restauración — comida (restaurant.food)',
    );
  });
});
