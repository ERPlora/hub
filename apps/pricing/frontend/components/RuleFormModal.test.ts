// PRICING-F10 and F11: «New discount rule» asks for Code, Name, Type with its value (a percent, an amount
// per unit, buy and free units, or tiers by quantity), what it applies to (with its category, product or
// service searched in Inventory or Services), and Customer group, Minimum quantity, From, Until and
// Priority. A row's Edit opens «Editing rule — {name}» and sends only what changed. Refusals stay in the
// dialog, under their field.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { business, JAPANESE, KUWAITI, POLISH, rule } from '../__tests__/fixtures';
import { click, ionValue, mountPricing, settle } from '../__tests__/mount-pricing';
import RuleFormModal from './RuleFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountPricing(RuleFormModal, { props: { open: false, rule: null, ...props }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`pricing-rule-form-${name}`) as Control;
  const save = () => m.inDoc('pricing-rule-form-submit') as Control;
  const combo = (testid: string) =>
    m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === `pricing-rule-form-${testid}`)!;
  async function pick(testid: string, option: { id: string; label: string } | null) {
    combo(testid).vm.$emit('update:modelValue', option);
    await settle();
  }
  return { ...m, field, save, combo, pick };
}

async function named(s: Awaited<ReturnType<typeof setup>>, code = 'TEN', name = 'Ten off') {
  await ionValue(s.field('code'), code, 'ionInput');
  await ionValue(s.field('name'), name, 'ionInput');
}

describe('RuleFormModal', () => {
  it('asks for a percent by default, for everything, every customer, with priority 100', async () => {
    const s = await setup();
    expect(s.inDoc('pricing-rule-form')?.getAttribute('aria-label')).toBe('New discount rule');
    expect([s.field('rule_type').value, s.field('applies_to').value, s.field('priority').value]).toEqual(['percent', 'all', '100']);
    expect(s.field('percent').label).toBe('Percent (%)');
    expect((s.field('min_quantity') as Control & { helperText?: string }).helperText).toBe(
      "Counted in the unit of each item's price: kg for one priced per kg.",
    );
    expect(s.combo('target')).toBeUndefined();
    expect(s.combo('group').props('placeholder')).toBe('Every customer');
    await named(s);
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('percent'), '12,5', 'ionInput');
    expect(s.save().disabled).toBe(false);
  });

  it('creates a percent rule on a category for a customer group', async () => {
    const s = await setup();
    s.answer(201, rule());
    await named(s, 'COL', 'Colour 10');
    await ionValue(s.field('percent'), '10', 'ionInput');
    await ionValue(s.field('applies_to'), 'category');
    expect(s.combo('target').props('label')).toBe('Category');
    expect(s.save().disabled).toBe(true);
    await s.pick('target', { id: 'c1', label: 'Colour' });
    await s.pick('group', { id: 'g1', label: 'VIP' });
    await ionValue(s.field('min_quantity'), '2', 'ionInput');
    await ionValue(s.field('valid_from'), '2026-07-01', 'ionInput');
    await ionValue(s.field('priority'), '5', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/pricing/rules',
        query: {},
        body: {
          code: 'COL',
          name: 'Colour 10',
          rule_type: 'percent',
          percent: '10',
          applies_to: 'category',
          category_id: 'c1',
          customer_group_id: 'g1',
          min_quantity: '2',
          valid_from: '2026-07-01',
          valid_until: null,
          priority: 5,
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an amount per unit, buy X get Y and tiers carry their own values', async () => {
    const s = await setup();
    s.answer(201, rule());
    await named(s, 'FIX', 'Fifty off');
    await ionValue(s.field('rule_type'), 'fixed');
    expect(s.inDoc('pricing-rule-form-percent')).toBeNull();
    await ionValue(s.field('amount'), '0,50', 'ionInput');
    await click(s.save());
    expect(s.sent()[0].body).toMatchObject({ rule_type: 'fixed', amount: 50 });
    expect(s.sent()[0].body).not.toHaveProperty('percent');

    const b = await setup();
    b.answer(201, rule());
    await named(b, 'BOGO', '2x1');
    await ionValue(b.field('rule_type'), 'buy_x_get_y');
    await ionValue(b.field('buy_quantity'), '2', 'ionInput');
    await ionValue(b.field('get_quantity'), '1', 'ionInput');
    await ionValue(b.field('applies_to'), 'service');
    await b.pick('target', { id: 's1', label: 'Haircut' });
    await click(b.save());
    expect(b.sent()[0].body).toMatchObject({ rule_type: 'buy_x_get_y', buy_quantity: 2, get_quantity: 1, applies_to: 'service', service_id: 's1' });

    const v = await setup();
    v.answer(201, rule());
    await named(v, 'VOL', 'Volume');
    await ionValue(v.field('rule_type'), 'tiered');
    await ionValue(v.field('tier-0-min_quantity'), '3', 'ionInput');
    await ionValue(v.field('tier-0-percent'), '10', 'ionInput');
    await click(v.field('add-tier'));
    await ionValue(v.field('tier-1-min_quantity'), '6', 'ionInput');
    await ionValue(v.field('tier-1-percent'), '15,5', 'ionInput');
    await click(v.save());
    expect(v.sent()[0].body).toMatchObject({
      rule_type: 'tiered',
      tiers: [
        { min_quantity: '3', percent: '10' },
        { min_quantity: '6', percent: '15.5' },
      ],
    });
  });

  it('an amount per unit is typed in the business’s currency: in Poland «0,50 zł», never a euro one', async () => {
    const s = await setup();
    await s.live();
    await s.result('base.business.get', business(POLISH));
    s.answer(201, rule());
    await named(s, 'FIX', 'Fifty off');
    await ionValue(s.field('rule_type'), 'fixed');
    await ionValue(s.field('amount'), '0,50 €', 'ionInput');
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('amount'), '0,50 zł', 'ionInput');
    await click(s.save());
    expect(s.sent()[0].body).toMatchObject({ rule_type: 'fixed', amount: 50 });
  });

  it('a refusal is said under its field and what was typed stays', async () => {
    const s = await setup();
    const message = 'A discount rule with that code already exists. Pick a different code.';
    s.answer(409, { error: { code: 'pricing.duplicate_code', message, fields: { code: message } } });
    await named(s);
    await ionValue(s.field('percent'), '10', 'ionInput');
    await click(s.save());
    expect(s.field('code').errorText).toBe(message);
    expect(s.field('code').value).toBe('TEN');
  });

  it('edits a rule sending only what changed, its new type with its value', async () => {
    const s = await setup({ rule: rule({ applies_to: 'product', product_id: 'p1', product_name: 'Shampoo', min_quantity: '2.000' }) });
    expect(s.inDoc('pricing-rule-form')?.getAttribute('aria-label')).toBe('Editing rule — Ten off');
    expect([s.field('percent').value, s.field('min_quantity').value]).toEqual(['10', '2']);
    expect(s.combo('target').props('modelValue')).toEqual({ id: 'p1', label: 'Shampoo' });
    s.answer(200, rule());
    await ionValue(s.field('name'), 'Ten off shampoo', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/rules/update', query: {}, body: { id: 'r1', name: 'Ten off shampoo' } }]);

    const f = await setup({ rule: rule() });
    f.answer(200, rule());
    await ionValue(f.field('rule_type'), 'fixed');
    await ionValue(f.field('amount'), '1', 'ionInput');
    await click(f.save());
    expect(f.sent()[0].body).toEqual({ id: 'r1', rule_type: 'fixed', amount: 100 });
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.inDoc('pricing-rule-form')?.getAttribute('aria-label')).toBe('Nueva regla de descuento');
    expect([s.field('percent').label, s.field('applies_to').label]).toEqual(['Porcentaje (%)', 'Se aplica a']);
  });
});

describe('RuleFormModal: the business answers after the form opened', () => {
  const NOT_AMOUNT = 'This is not an amount. Type a figure, for example 12.50.';
  const FIXED = { rule_type: 'fixed' as const, percent: null };

  it('an untouched amount per unit is rewritten from the rule with the yen’s decimals, and «Save» keeps its scale', async () => {
    const s = await setup({ rule: rule({ ...FIXED, amount: 150 }) });
    expect(s.field('amount').value).toBe('1.50');
    await s.live();
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('amount').value).toBe('150');
    s.answer(200, rule({ ...FIXED, amount: 150, name: 'Ten yen off' }));
    await ionValue(s.field('name'), 'Ten yen off', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/rules/update', query: {}, body: { id: 'r1', name: 'Ten yen off' } }]);
  });

  it('with three decimals an untouched amount per unit is rewritten in that scale, never saved ten times bigger', async () => {
    const s = await setup({ rule: rule({ ...FIXED, amount: 1500 }) });
    expect(s.field('amount').value).toBe('15.00');
    await s.live();
    await s.result('base.business.get', business(KUWAITI));
    expect(s.field('amount').value).toBe('1.500');
    s.answer(200, rule({ ...FIXED, amount: 1500, name: 'Dinar off' }));
    await ionValue(s.field('name'), 'Dinar off', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/rules/update', query: {}, body: { id: 'r1', name: 'Dinar off' } }]);
  });

  it('what the person already typed stays and is read in the business’s currency: «2,50» in Poland is 250 grosze', async () => {
    const s = await setup();
    s.answer(201, rule());
    await named(s, 'FIX', 'Fifty off');
    await ionValue(s.field('rule_type'), 'fixed');
    await ionValue(s.field('amount'), '2,50', 'ionInput');
    await s.live();
    await s.result('base.business.get', business(POLISH));
    expect(s.field('amount').value).toBe('2,50');
    await click(s.save());
    expect(s.sent()[0].body).toMatchObject({ rule_type: 'fixed', amount: 250 });
  });

  it('what the person typed that the yen cannot read stays as typed: «Save» waits, nothing is sent (never a 0) and the field says why', async () => {
    const s = await setup({ rule: rule({ ...FIXED, amount: 150 }) });
    await ionValue(s.field('amount'), '1,75', 'ionInput');
    await s.live();
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('amount').value).toBe('1,75');
    expect(s.save().disabled).toBe(true);
    await click(s.save());
    expect(s.sent()).toEqual([]);
    s.field('amount').dispatchEvent(new CustomEvent('ionBlur'));
    await settle();
    expect(s.field('amount').value).toBe('1,75');
    expect(s.field('amount').errorText).toBe(NOT_AMOUNT);
  });
});
