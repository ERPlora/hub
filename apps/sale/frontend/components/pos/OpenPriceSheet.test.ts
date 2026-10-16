// The open-price sheet (SALE-F09): the amount typed on the keypad, «Section (VAT)» and «Add
// <amount>», which cannot be pressed without an amount and a department. It hands the line up in cents
// with its department (or, without departments, its tax category): the server names the line after it.
// A refusal is read in the sheet.
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import { page } from './__tests__/fixtures';
import OpenPriceSheet from './OpenPriceSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const department = { id: 'd1', name: 'Fruta', tax_category_key: 'food', tax_category_name: 'Food', tax_rate_pct: '4.00', sort_order: 0 };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const open = ref(true);
  const extra = ref(props);
  const m = await mountSale(
    {
      setup: () => () =>
        h(OpenPriceSheet, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), pending: false, error: null, ...extra.value }),
    },
    { locale },
  );
  await settle();
  await m.live();
  const press = async (...keys: string[]) => {
    for (const key of keys) await click(m.find(`pos-key-${key}`).element);
  };
  const add = () => m.find('pos-open-price-add');
  const disabled = () => (add().element as HTMLElement & { disabled?: boolean }).disabled === true;
  const sheet = () => m.wrapper.findComponent(OpenPriceSheet);
  return { ...m, open, extra, press, add, disabled, sheet };
}

describe('OpenPriceSheet', () => {
  it('is «Open price» with the amount typed on top', async () => {
    const m = await setup({}, 'es');
    expect(m.find('pos-open-price-title').text()).toBe('Precio libre');
    expect(plain(m.find('pos-open-price-amount').text())).toBe('0,00 €');
    await m.press('1', '2', 'dot', '5');
    expect(plain(m.find('pos-open-price-amount').text())).toBe('12,50 €');
    expect(m.find('pos-open-price-department-label').text()).toBe('Sección (IVA)');
  });

  it('«Add» waits for an amount and a department, then hands the line up in cents', async () => {
    const m = await setup({}, 'es');
    expect(m.disabled()).toBe(true);
    await m.press('3');
    expect(m.disabled()).toBe(true);
    await m.result('sale.department.list', page([department]));
    await click(m.find('pos-department-d1').element);
    expect(m.disabled()).toBe(false);
    expect(plain(m.add().text())).toBe('Añadir 3,00 €');
    await click(m.add().element);
    expect(m.sheet().emitted('add')).toEqual([[{ unit_price: 300, department_id: 'd1' }]]);
  });

  it('without departments the line goes with the tax category chosen in the app’s picker', async () => {
    const m = await setup();
    await m.press('5');
    await m.result('sale.department.list', page([]));
    await m.reopen();
    await m.result(
      'tax.category.list',
      page([{ id: 'k', key: 'food', name: 'Food', description: '', display_name: 'Food', display_description: '', is_system: true, is_active: true, rate_pct: '10.00', operation_class: 'subject' }]),
    );
    await click(m.find('pos-tax-category').element);
    await click(m.find('pos-tax-category-option').element);
    await click(m.add().element);
    expect(m.sheet().emitted('add')).toEqual([[{ unit_price: 500, tax_category_key: 'food' }]]);
  });

  it('a refusal is read in the sheet; while the line is on its way «Add» waits', async () => {
    const m = await setup({ error: 'You do not have permission.', pending: true });
    expect(m.find('pos-open-price-error').text()).toBe('You do not have permission.');
    expect(m.disabled()).toBe(true);
  });

  it('opens blank every time', async () => {
    const m = await setup();
    await m.press('9');
    m.open.value = false;
    await settle();
    m.open.value = true;
    await settle();
    expect(plain(m.find('pos-open-price-amount').text())).toBe('€0.00');
  });
});
