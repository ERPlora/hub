// `taxLabel(name, rate, locale)`: how a department's VAT reads — in its row («VAT charged») and among the
// choices of its picker —, as the old screen did: «Display name · 4%». The rate is the server's (today's
// in the business's country), formatted in the page's language; no rule, the name alone; no name, the
// key the server sent.
import { describe, expect, it } from 'vitest';

import { plain } from './format';
import { taxLabel } from './taxLabel';

describe('taxLabel', () => {
  it('is «name · rate», the rate in the page’s language', () => {
    expect(plain(taxLabel('Superreducido', '4.00', 'en'))).toBe('Superreducido · 4%');
    expect(plain(taxLabel('Restauración — comida', '10.00', 'es'))).toBe('Restauración — comida · 10 %');
    expect(plain(taxLabel('Recargo', '5.20', 'es'))).toBe('Recargo · 5,2 %');
  });

  it('without a rate today, the name alone', () => {
    expect(taxLabel('Books', null, 'en')).toBe('Books');
  });

  it('a blank name falls back to what the server named it by', () => {
    expect(taxLabel('  ', '21.00', 'en', 'general')).toBe('general · 21%');
  });
});
