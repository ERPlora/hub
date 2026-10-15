// What the rules table paints: the VALUE of a rule with its unit (the old module's pricing#28: one column,
// «10 %», «0,50 € por unidad», never a bare 0), what it applies to (with its group), and the tax basis of
// a price list (an empty one follows the business, and says so).
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { rule } from '../__tests__/fixtures';
import en from '../locale/en.json';
import es from '../locale/es.json';
import { appliesToLabel, ruleValueLabel, taxBasisLabel } from './rules';

function translator(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return (key: string, named?: Record<string, unknown>) => (named ? i18n.global.t(key, named) : i18n.global.t(key));
}

describe('ruleValueLabel', () => {
  it('paints each type with its unit', () => {
    const t = translator('es');
    expect(ruleValueLabel(rule({ percent: '12.50' }), t, 'es')).toBe('12,5\u00a0%');
    expect(ruleValueLabel(rule({ rule_type: 'fixed', percent: null, amount: 50 }), t, 'es')).toBe('0,50\u00a0€ por unidad');
    expect(ruleValueLabel(rule({ rule_type: 'buy_x_get_y', percent: null, buy_quantity: 2, get_quantity: 1 }), t, 'es')).toBe(
      'Compra 2, llévate 1',
    );
    const tiers = [
      { min_quantity: '3.000', percent: '10.00' },
      { min_quantity: '6.000', percent: '15.00' },
    ];
    expect(ruleValueLabel(rule({ rule_type: 'tiered', percent: null, tiers }), t, 'es')).toBe('3+: 10\u00a0% · 6+: 15\u00a0%');
    expect(ruleValueLabel(rule({ rule_type: 'fixed', percent: null, amount: 50 }), translator('en'), 'en')).toBe('€0.50 per unit');
  });
});

describe('appliesToLabel', () => {
  it('names the scope, or its target, and the group after it', () => {
    const t = translator('en');
    expect(appliesToLabel(rule(), t)).toBe('Everything');
    expect(appliesToLabel(rule({ applies_to: 'services' }), t)).toBe('All services');
    expect(appliesToLabel(rule({ applies_to: 'category', category_id: 'c1', category_name: 'Colour' }), t)).toBe('Colour');
    expect(appliesToLabel(rule({ applies_to: 'service', service_id: 's1', service_name: 'Haircut' }), t)).toBe('Haircut');
    // Inventory deleted its product or category: said until the reaction switches the rule off.
    const gone = rule({ applies_to: 'product', product_id: 'p1', product_name: 'Shampoo', target_deleted: true });
    expect(appliesToLabel(gone, t)).toBe('Shampoo (deleted)');
    expect(appliesToLabel(gone, translator('es'))).toBe('Shampoo (borrado)');
    expect(appliesToLabel(rule({ customer_group_id: 'g1', customer_group_name: 'VIP' }), t)).toBe('Everything · VIP');
    // A group deleted in Customers has no name any more: it says so.
    expect(appliesToLabel(rule({ customer_group_id: 'g1', customer_group_name: null }), t)).toBe('Everything · Deleted group');
    expect(appliesToLabel(rule({ customer_group_id: 'g1', customer_group_name: null }), translator('es'))).toBe('Todo · Grupo borrado');
  });
});

describe('taxBasisLabel', () => {
  it('says the business default for an empty one', () => {
    const t = translator('es');
    expect([null, true, false].map((value) => taxBasisLabel(value, t))).toEqual([
      'Según el negocio',
      'Impuesto incluido',
      'Impuesto no incluido',
    ]);
  });
});
