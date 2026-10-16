// PRICING-F04 and F05: the two confirmations of a price list. «Make {name} the general list?» says that
// it will apply to every customer and that the current one stops being general; «Deactivate {name}?» says
// it stops applying to new sales and keeps its prices. Confirming runs the command and closes; a refusal
// stays in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { priceList } from '../__tests__/fixtures';
import { click, mountPricing, settle } from '../__tests__/mount-pricing';
import ListConfirm from './ListConfirm.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(action: 'default' | 'deactivate', locale: 'en' | 'es' = 'en') {
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

  it('speaks Spanish', async () => {
    const s = await setup('deactivate', 'es');
    expect(s.inDoc('pricing-list-deactivate')?.getAttribute('aria-label')).toBe('¿Desactivar VIP members?');
  });
});
