// PRICING-F02 and F03: «New price list» asks for Code and Name (required), Currency (the business's, its
// country's: EUR in Spain, PLN in Poland; flow pricing-business-currency), Tax (Business
// default, Tax included, Tax excluded), Customer group (searched in Customers; empty = no group), From,
// Until and «General list» (not with a group). A row's Edit opens «Editing price list — {name}» and sends
// only what changed (no group = `customer_group_id: null`). Refusals stay in the dialog, under their field.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { Business } from '../../../../base/frontend/operations';
import { business, POLISH, priceList } from '../__tests__/fixtures';
import { click, ionChecked, ionValue, mountPricing, settle } from '../__tests__/mount-pricing';
import PriceListFormModal from './PriceListFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; checked?: boolean };

/** The dialog open, with the hub's business answered (`null`: it has not answered yet). */
async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en', owner: Business | null = business()) {
  const m = await mountPricing(PriceListFormModal, { props: { open: false, priceList: null, ...props }, locale });
  await m.live();
  if (owner) await m.result('base.business.get', owner);
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`pricing-list-form-${name}`) as Control;
  const save = () => m.inDoc('pricing-list-form-submit') as Control;
  const group = () => m.wrapper.findComponent(Combo);
  return { ...m, field, save, group };
}

describe('PriceListFormModal', () => {
  it('asks for every field of a new list and needs code and name', async () => {
    const s = await setup();
    expect(s.inDoc('pricing-list-form')?.getAttribute('aria-label')).toBe('New price list');
    expect(['code', 'name', 'currency', 'tax', 'valid_from', 'valid_until', 'is_default'].map((name) => s.field(name).label ?? s.field(name).textContent?.trim())).toEqual([
      'Code',
      'Name',
      'Currency',
      'Tax',
      'From',
      'Until',
      'General list',
    ]);
    expect([s.field('currency').value, s.field('tax').value]).toEqual(['EUR', 'business']);
    expect(s.group().props('label')).toBe('Customer group');
    expect(s.save().textContent).toContain('Create');
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('code'), 'VIP', 'ionInput');
    await ionValue(s.field('name'), 'VIP members', 'ionInput');
    expect(s.save().disabled).toBe(false);
  });

  it('creates the list with what was typed and closes', async () => {
    const s = await setup();
    s.answer(201, priceList());
    await ionValue(s.field('code'), ' VIP ', 'ionInput');
    await ionValue(s.field('name'), ' VIP members ', 'ionInput');
    await ionValue(s.field('currency'), 'usd', 'ionInput');
    await ionValue(s.field('tax'), 'included');
    s.group().vm.$emit('update:modelValue', { id: 'g1', label: 'VIP' });
    await settle();
    await ionValue(s.field('valid_from'), '2026-07-01', 'ionInput');
    await ionValue(s.field('valid_until'), '2026-08-31', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/pricing/price_lists',
        query: {},
        body: {
          code: 'VIP',
          name: 'VIP members',
          currency: 'USD',
          tax_included: true,
          customer_group_id: 'g1',
          valid_from: '2026-07-01',
          valid_until: '2026-08-31',
          is_default: false,
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a general list is for everybody: the switch goes off with a group', async () => {
    const s = await setup();
    s.answer(201, priceList({ is_default: true, customer_group_id: null }));
    await ionValue(s.field('code'), 'GEN', 'ionInput');
    await ionValue(s.field('name'), 'General', 'ionInput');
    await ionChecked(s.field('is_default'), true);
    s.group().vm.$emit('update:modelValue', { id: 'g1', label: 'VIP' });
    await settle();
    expect([s.field('is_default').checked, s.field('is_default').disabled]).toEqual([false, true]);
    s.group().vm.$emit('update:modelValue', null);
    await settle();
    await ionChecked(s.field('is_default'), true);
    await click(s.save());
    expect(s.sent()[0].body).toMatchObject({ code: 'GEN', customer_group_id: null, tax_included: null, is_default: true });
  });

  it('a new list proposes the business’s currency: in Poland PLN, which can be the general one and the euro not', async () => {
    const s = await setup({}, 'en', business(POLISH));
    expect(s.field('currency').value).toBe('PLN');
    expect(s.field('is_default').disabled).toBe(false);
    await ionChecked(s.field('is_default'), true);
    await ionValue(s.field('currency'), 'eur', 'ionInput');
    expect([s.field('is_default').checked, s.field('is_default').disabled]).toEqual([false, true]);
    await ionValue(s.field('currency'), 'pln', 'ionInput');
    expect(s.field('is_default').disabled).toBe(false);
    s.answer(201, priceList({ currency: 'PLN' }));
    await ionValue(s.field('code'), 'VIP', 'ionInput');
    await ionValue(s.field('name'), 'VIP members', 'ionInput');
    await click(s.save());
    expect(s.sent()[0].body).toMatchObject({ code: 'VIP', currency: 'PLN' });
  });

  it('until the business answers, the currency is empty and the list cannot be general; the answer fills it', async () => {
    const s = await setup({}, 'en', null);
    expect([s.field('currency').value, s.field('is_default').disabled]).toEqual(['', true]);
    await s.result('base.business.get', business(POLISH));
    await settle();
    expect([s.field('currency').value, s.field('is_default').disabled]).toEqual(['PLN', false]);
  });

  it('what the person typed in Currency stays when the business answers', async () => {
    const s = await setup({}, 'en', null);
    await ionValue(s.field('currency'), 'usd', 'ionInput');
    await s.result('base.business.get', business(POLISH));
    await settle();
    expect(s.field('currency').value).toBe('usd');
  });

  it('an emptied Currency sends none: the server takes the business’s', async () => {
    const s = await setup({}, 'en', business(POLISH));
    s.answer(201, priceList({ currency: 'PLN' }));
    await ionValue(s.field('code'), 'VIP', 'ionInput');
    await ionValue(s.field('name'), 'VIP members', 'ionInput');
    await ionValue(s.field('currency'), ' ', 'ionInput');
    await click(s.save());
    expect(s.sent()[0].body).not.toHaveProperty('currency');
  });

  it('a general list goes in the business’s currency: the switch goes off with another currency', async () => {
    const s = await setup();
    await ionChecked(s.field('is_default'), true);
    await ionValue(s.field('currency'), 'usd', 'ionInput');
    expect([s.field('is_default').checked, s.field('is_default').disabled]).toEqual([false, true]);
    await ionValue(s.field('currency'), 'eur', 'ionInput');
    expect(s.field('is_default').disabled).toBe(false);
  });

  it('a repeated code is said under its field and what was typed stays', async () => {
    const s = await setup();
    const message = 'A price list with that code already exists. Pick a different code.';
    s.answer(409, { error: { code: 'pricing.duplicate_code', message, fields: { code: message } } });
    await ionValue(s.field('code'), 'VIP', 'ionInput');
    await ionValue(s.field('name'), 'Again', 'ionInput');
    await click(s.save());
    expect(s.field('code').errorText).toBe(message);
    expect(s.field('code').value).toBe('VIP');
  });

  it('edits a list sending only what changed, the group taken off as null', async () => {
    const s = await setup({ priceList: priceList({ tax_included: false, valid_from: '2026-07-01' }) });
    expect(s.inDoc('pricing-list-form')?.getAttribute('aria-label')).toBe('Editing price list — VIP members');
    expect(s.inDoc('pricing-list-form-is_default')).toBeNull();
    expect([s.field('code').value, s.field('tax').value, s.field('valid_from').value]).toEqual(['VIP', 'excluded', '2026-07-01']);
    expect(s.group().props('modelValue')).toEqual({ id: 'g1', label: 'VIP' });
    expect(s.save().textContent).toContain('Save');
    s.answer(200, priceList());
    await ionValue(s.field('name'), 'VIP club', 'ionInput');
    s.group().vm.$emit('update:modelValue', null);
    await settle();
    await ionValue(s.field('valid_from'), '', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/pricing/price_lists/update',
        query: {},
        body: { id: 'l1', name: 'VIP club', customer_group_id: null, valid_from: null },
      },
    ]);
  });

  it('a group deleted in Customers is named as such in the picker', async () => {
    const s = await setup({ priceList: priceList({ customer_group_id: 'g9', customer_group_name: null }) });
    expect(s.group().props('modelValue')).toEqual({ id: 'g9', label: 'Deleted group' });
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.inDoc('pricing-list-form')?.getAttribute('aria-label')).toBe('Nueva tarifa');
    expect([s.field('currency').label, s.field('tax').label]).toEqual(['Divisa', 'Impuesto']);
  });
});
