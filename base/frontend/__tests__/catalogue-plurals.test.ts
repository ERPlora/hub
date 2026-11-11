// The shared check that no catalogue spells a plural with «(s)» (hub#1124): what it catches and what it lets through.
import { describe, expect, it } from 'vitest';

import { pluralsInParentheses } from './catalogue-plurals';

const catalogue = (entries: Record<string, string>): Map<string, string> => new Map(Object.entries(entries));

describe('pluralsInParentheses', () => {
  it('names every message that spells a plural in parentheses, in each catalogue it is given', () => {
    const en = catalogue({ 'a.import': 'Import {n} product(s)', 'a.links': 'It stops applying to {count} category(ies)', 'a.ok': 'Add {n} selected' });
    const es = catalogue({ 'a.import': 'Importar {n} producto(s)', 'a.options': 'Se borrarán {count} opción(es)', 'a.ok': 'Añadir {n} seleccionado | Añadir {n} seleccionados' });
    expect(pluralsInParentheses(en, es)).toEqual([
      'a.import: Import {n} product(s)',
      'a.links: It stops applying to {count} category(ies)',
      'a.import: Importar {n} producto(s)',
      'a.options: Se borrarán {count} opción(es)',
    ]);
  });

  it('lets through the forms of vue-i18n and the parentheses that are not a plural', () => {
    const messages = catalogue({
      plural: '{n} row | {n} rows',
      count: 'Tick all of «{category}» ({n})',
      note: 'Slug (optional)',
      unit: 'Price (€)',
      sent: 'Send the order (3)',
    });
    expect(pluralsInParentheses(messages)).toEqual([]);
  });
});
