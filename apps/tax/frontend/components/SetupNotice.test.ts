// TAX-F17 — the step «Your taxes» above the tax lists: while no active root rule applies today
// (`tax.rule.status`, any country: the Hub does not keep the business's yet), whoever can manage taxes
// reads «Set up the VAT rates of the country you sell in…» with «Set up», which takes them to Rules.
// Configured, it is gone. Each page mounts it only for whoever can manage taxes (its own tests).
import { describe, expect, it } from 'vitest';

import { click, mountTax, settle } from '../__tests__/mount-tax';
import SetupNotice from './SetupNotice.vue';

const OP = 'tax.rule.status';
const MISSING = { country_code: null, matching_rules: 0, configured: false };
const CONFIGURED = { country_code: null, matching_rules: 11, configured: true };

async function setup(options: { path?: string; locale?: 'en' | 'es' } = {}) {
  return mountTax(SetupNotice, { path: options.path ?? '/tax/categories', locale: options.locale });
}

describe('SetupNotice (TAX-F17)', () => {
  it('asks the server whether any rule applies today, in any country', async () => {
    const m = await setup();
    await m.live();
    expect(m.params(OP)).toEqual([{}]);
  });

  it('says what is missing while nothing applies, with «Set up» to Rules', async () => {
    const m = await setup();
    await m.live();
    await m.result(OP, MISSING);
    const notice = m.find('tax-setup');
    expect(notice.exists()).toBe(true);
    expect(notice.text()).toContain('Your taxes');
    expect(notice.text()).toContain('Set up the VAT rates of the country you sell in so the till can price a sale.');
    await click(m.find('tax-setup-action').element);
    await settle();
    expect(m.router.currentRoute.value.path).toBe('/tax/rules');
  });

  it('on Rules itself it has no button: the «+» of the table is right there', async () => {
    const m = await setup({ path: '/tax/rules' });
    await m.live();
    await m.result(OP, MISSING);
    expect(m.find('tax-setup').exists()).toBe(true);
    expect(m.find('tax-setup-action').exists()).toBe(false);
  });

  it('is gone once a rule applies, and before the server answers', async () => {
    const m = await setup();
    await m.live();
    expect(m.find('tax-setup').exists()).toBe(false);
    await m.result(OP, CONFIGURED);
    expect(m.find('tax-setup').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const m = await setup({ locale: 'es' });
    await m.live();
    await m.result(OP, MISSING);
    expect(m.find('tax-setup').text()).toContain('Tus impuestos');
    expect(m.find('tax-setup').text()).toContain(
      'Configura los tipos de IVA del país en el que vendes para que el TPV pueda calcular el precio de una venta.',
    );
    expect(m.find('tax-setup-action').text()).toBe('Configurar');
  });
});
