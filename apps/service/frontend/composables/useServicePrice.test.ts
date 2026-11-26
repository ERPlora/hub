// A service's price as it is sold, written the same wherever a service is offered (the till's tile, the public
// booking page): a fixed price is its amount; any other says how it is priced.
import { createShellI18n } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import en from '../locale/en.json';
import es from '../locale/es.json';
import type { PricingType } from '../operations';
import { useServicePrice } from './useServicePrice';

function priced(locale: 'en' | 'es', amount: string, type: PricingType): string {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  const wrapper = mount(
    defineComponent({
      setup() {
        const servicePrice = useServicePrice();
        return () => h('p', servicePrice(amount, type));
      },
    }),
    { global: { plugins: [i18n] } },
  );
  return wrapper.text();
}

describe('useServicePrice', () => {
  it.each([
    ['fixed', '€65.00', '65,00 €'],
    ['from', 'From €65.00', 'Desde 65,00 €'],
    ['hourly', '€65.00 / hour', '65,00 € / hora'],
    ['variable', 'Variable · €65.00', 'Variable · 65,00 €'],
    ['free', 'Free', 'Gratis'],
  ] as const)('a %s price, in English and in Spanish', (type, english, spanish) => {
    expect(priced('en', '€65.00', type)).toBe(english);
    expect(priced('es', '65,00 €', type)).toBe(spanish);
  });
});
