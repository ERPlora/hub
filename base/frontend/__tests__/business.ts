// What the platform's `base.business.get` answers, for the tests of base and of every app whose screens paint the
// business's money (BASE-F50): one fixture, so a field the business gains is added once. Free of side effects: an
// app's test helper imports it without mounting base.
import type { Business } from '../operations';

/** A business in Spain, in euros; `fields` change it (BASE-G98: amounts are in its currency). */
export function business(fields: Partial<Business> = {}): Business {
  return {
    name: 'Bar Pepe',
    country: 'ES',
    country_name: 'Spain',
    timezone: 'Europe/Madrid',
    language: 'es',
    language_name: 'Spanish',
    currency: 'EUR',
    currency_label: 'EUR · Euro',
    currency_decimals: 2,
    demo: false,
    settings_url: 'https://erplora.com/hubs/bar-pepe/settings',
    ...fields,
  };
}

/** A business in Poland: it pays in złoty. */
export const POLISH: Partial<Business> = { country: 'PL', country_name: 'Poland', currency: 'PLN', currency_label: 'PLN · Polish Zloty' };
