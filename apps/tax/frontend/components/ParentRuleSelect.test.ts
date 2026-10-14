// «Root rule (component of)» of a new rule (TAX-F06): the roots it may hang from are the SERVER's to
// say (`tax.rule.parent_candidates`, the predicate `tax.rule.create` checks), asked for the country,
// region, category and rate of the form — a root that starts in 2027 included (TAX-F07 then F06). Until
// the country and the category are chosen nothing is asked and the box says there is no root.
import { describe, expect, it } from 'vitest';

import type { RuleOut } from '../operations';
import { flush, mountTax } from '../__tests__/mount-tax';
import ParentRuleSelect from './ParentRuleSelect.vue';

type Control = HTMLElement & { value?: unknown; placeholder?: string; disabled?: boolean; label?: string; errorText?: string };

const OP = 'tax.rule.parent_candidates';

const root = (id: string, over: Partial<RuleOut> = {}): RuleOut => ({
  id,
  country_code: 'ES',
  region_code: null,
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restaurant — food',
  rate_pct: '10.00',
  tax_type: 'vat',
  operation_class: 'subject',
  exempt_reason: null,
  regime_key: null,
  parent_id: null,
  component_label: null,
  valid_from: '2027-01-01',
  valid_to: null,
  is_active: true,
  updated_at: '2026-10-13T10:00:00Z',
  ...over,
});

const SLOT = { country: 'ES', region: '', category: 'restaurant.food', rate: '' };

async function setup(props: Record<string, unknown> = SLOT, locale: 'en' | 'es' = 'en') {
  const m = await mountTax(ParentRuleSelect, { props: { modelValue: '', ...props }, locale, path: '/tax/rules' });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: string) => m.wrapper.setProps({ modelValue: value }) });
  // No slot, no subscription: no stream to open either.
  if (m.client.stream.subscriptions(OP).length) await m.live();
  const select = () => m.inDoc('tax-rule-form-parent_id') as Control;
  const options = () => [...select().querySelectorAll('ion-select-option')].map((o) => [(o as Control).value, o.textContent?.trim()]);
  return { ...m, select, options };
}

describe('ParentRuleSelect (TAX-F06)', () => {
  it('asks nothing until the country and the category are chosen, and says there is no root', async () => {
    const s = await setup({ country: '', region: '', category: 'restaurant.food', rate: '' });
    expect(s.params(OP)).toEqual([]);
    expect([s.select().label, s.select().disabled, s.select().placeholder]).toEqual([
      'Root rule (component of)',
      true,
      'No compatible root rule for this country/region/category',
    ]);
  });

  it('asks the server for the roots of the slot, and offers «None» and what it answers — a 2027 root too', async () => {
    const s = await setup({ ...SLOT, region: 'ES-CN', rate: '1.4' });
    expect(s.params(OP)).toEqual([{ country_code: 'ES', region_code: 'ES-CN', tax_category_key: 'restaurant.food', rate_pct: '1.4', limit: 50 }]);
    await s.result(OP, { rows: [root('future'), root('old', { valid_from: null, is_active: false, rate_pct: '21' })], total: 2, limit: 50, offset: 0 });
    expect([s.select().disabled, s.select().placeholder]).toEqual([false, 'Choose a root rule']);
    expect(s.options()).toEqual([
      ['', 'None (this is a root rule)'],
      ['future', '10.00% · VAT · Jan 1, 2027'],
      ['old', '21.00% · VAT · deactivated'],
    ]);
  });

  it('a rate still being typed is not sent: the server reads a missing rate as one that charges tax', async () => {
    const s = await setup({ ...SLOT, rate: '1.' });
    expect(s.params(OP)[0]).not.toHaveProperty('rate_pct');
    await s.wrapper.setProps({ rate: '0' });
    await s.reopen();
    expect(s.params(OP)[0]).toMatchObject({ rate_pct: '0' });
  });

  it('with no root to offer it stays disabled', async () => {
    const s = await setup();
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.select().disabled).toBe(true);
  });

  it('a chosen root the server no longer offers is dropped', async () => {
    const s = await setup({ ...SLOT, modelValue: 'future' });
    await s.result(OP, { rows: [root('future')], total: 1, limit: 50, offset: 0 });
    expect(s.wrapper.emitted('update:modelValue')).toBeUndefined();
    await s.result(OP, { rows: [root('other')], total: 1, limit: 50, offset: 0 }, {}, 2);
    expect(s.wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['']);
  });

  it('speaks Spanish, with the rate and the day as a Spanish reader writes them', async () => {
    const s = await setup(SLOT, 'es');
    await s.result(OP, { rows: [root('future')], total: 1, limit: 50, offset: 0 });
    expect(String(s.options()[1][1]).replace(/[  ]/g, ' ')).toBe('10,00 % · IVA · 1 ene 2027');
    await flush();
  });
});
