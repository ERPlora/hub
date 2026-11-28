// PRICING-F04, F05 and F16: the three confirmations of a price list. «Make {name} the general list?» says that
// it will apply to every customer and that the current one stops being general; «Deactivate {name}?» says
// it stops applying to new sales and keeps its prices; «Delete {name}?» says it disappears with its prices and
// that sales already made do not change. Confirming runs the command and closes; a refusal stays in the dialog.
import { describe, expect, it } from 'vitest';

import { priceList } from '../__tests__/fixtures';
import { click, mountPricing, settle } from '../__tests__/mount-pricing';
import ListConfirm from './ListConfirm.vue';

async function setup(action: 'default' | 'deactivate' | 'delete', locale: 'en' | 'es' = 'en') {
  const m = await mountPricing(ListConfirm, { props: { list: priceList({ customer_group_id: null }), action: null }, locale });
  await m.wrapper.setProps({ 'onUpdate:action': (value: string | null) => m.wrapper.setProps({ action: value }) });
  await m.wrapper.setProps({ action });
  await settle();
  return m;
}

describe('ListConfirm', () => {
  it('asks before making a list general and runs it', async () => {
    const s = await setup('default');
    const dialog = s.inDoc('pricing-list-default');
    expect(dialog?.getAttribute('aria-label')).toBe('Make VIP members the general list?');
    expect(dialog?.textContent).toContain('it will apply to every customer');
    s.answer(200, priceList({ is_default: true }));
    await click(s.inDoc('pricing-list-default-submit'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/price_lists/set_default', query: {}, body: { id: 'l1' } }]);
    expect(s.wrapper.emitted('update:action')?.at(-1)).toEqual([null]);
  });

  it('asks before deactivating, and a refusal stays in the dialog', async () => {
    const s = await setup('deactivate');
    expect(s.inDoc('pricing-list-deactivate')?.textContent).toContain('will stop applying to new sales. Its prices are kept.');
    const message = 'This is the general price list: make another one general or take its mark off before deactivating it.';
    s.answer(409, { error: { code: 'pricing.price_list_is_default', message } });
    await click(s.inDoc('pricing-list-deactivate-submit'));
    expect(s.sent()[0]).toMatchObject({ path: '/api/pricing/price_lists/deactivate', body: { id: 'l1' } });
    expect(s.inDoc('pricing-list-deactivate-error')?.textContent).toContain(message);
    expect(s.wrapper.emitted('update:action')?.at(-1)).not.toEqual([null]);
  });

  it('asks before deleting a list, runs it and says it is gone', async () => {
    const s = await setup('delete');
    const dialog = s.inDoc('pricing-list-delete');
    expect(dialog?.getAttribute('aria-label')).toBe('Delete VIP members?');
    expect(dialog?.textContent).toContain('VIP members disappears with all its prices. Sales already made do not change.');
    s.answer(200, { id: 'l1', code: 'VIP' });
    await click(s.inDoc('pricing-list-delete-submit'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/price_lists/delete', query: {}, body: { id: 'l1' } }]);
    expect(s.wrapper.emitted('update:action')?.at(-1)).toEqual([null]);
    expect(s.wrapper.emitted('deleted')).toEqual([[]]);
  });

  it('a list someone else deleted first is refused inside the dialog, and nothing is said gone', async () => {
    const s = await setup('delete');
    s.answer(404, { error: { code: 'pricing.price_list_not_found', message: 'This price list does not exist.' } });
    await click(s.inDoc('pricing-list-delete-submit'));
    expect(s.inDoc('pricing-list-delete-error')?.textContent).toContain('This price list does not exist.');
    expect(s.wrapper.emitted('update:action')?.at(-1)).not.toEqual([null]);
    expect(s.wrapper.emitted('deleted')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('deactivate', 'es');
    expect(s.inDoc('pricing-list-deactivate')?.getAttribute('aria-label')).toBe('¿Desactivar VIP members?');
    const deleting = await setup('delete', 'es');
    expect(deleting.inDoc('pricing-list-delete')?.getAttribute('aria-label')).toBe('¿Borrar VIP members?');
    expect(deleting.inDoc('pricing-list-delete')?.textContent).toContain(
      'VIP members desaparece con todos sus precios. Las ventas ya hechas no cambian.',
    );
  });
});
