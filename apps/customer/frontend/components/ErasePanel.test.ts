// «Erase personal data» on the card (CUSTOMER-F16): «Erase personal data (GDPR)» says what it erases
// and that it cannot be undone, asks the «Reason (kept in the audit)» and, confirmed, erases; then
// «Personal data erased.». A refusal stays in the panel.
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, json, type MountOptions, mountCustomer, refusal, sent } from '../__tests__/mount-customer';
import ErasePanel from './ErasePanel.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(ErasePanel, { props: { customer: { id: 'c1', name: 'Ana García' } }, ...options });
  const click = async (id: string) => {
    await m.wrapper.get(`[data-testid="${id}"]`).trigger('click');
    await flush();
  };
  return { ...m, click };
}

describe('ErasePanel', () => {
  it('says what it erases and that it cannot be undone, and asks the reason', async () => {
    const s = await setup();
    expect(s.wrapper.get('h3').text()).toBe('Erase personal data (GDPR)');
    expect(s.wrapper.text()).toContain("This erases Ana García's personal data, their notes, their activity and their custom fields, and cannot be undone.");
    expect(s.wrapper.findComponent(IonInput).props('label')).toBe('Reason (kept in the audit)');
  });

  it('erases with the reason, says so and tells the card', async () => {
    const s = await setup();
    await s.wrapper.findComponent(IonInput).setValue(' Asked by email ');
    s.net.onApi(() => json({ id: 'c1' }));
    await s.click('customer-erase-submit');
    expect(sent(s.net.api[0])).toMatchObject({ path: '/api/customer/customers/erase', body: { id: 'c1', reason: 'Asked by email' } });
    expect(toastSuccess).toHaveBeenCalledWith('Personal data erased.');
    expect(s.wrapper.emitted('erased')).toHaveLength(1);
  });

  it('Cancel erases nothing', async () => {
    const s = await setup();
    await s.click('customer-erase-cancel');
    expect(s.wrapper.emitted('cancel')).toHaveLength(1);
    expect(s.net.api).toHaveLength(0);
  });

  it('a refusal stays in the panel', async () => {
    const s = await setup();
    s.net.onApi(() => refusal(403, 'permission_denied', 'You do not have permission to do that.'));
    await s.click('customer-erase-submit');
    expect(s.wrapper.get('[data-testid="customer-erase-error"]').text()).toContain('You do not have permission to do that.');
    expect(s.wrapper.emitted('erased')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.wrapper.get('h3').text()).toBe('Borrar datos personales (RGPD)');
    expect(s.wrapper.get('[data-testid="customer-erase-submit"]').text()).toBe('Borrar datos personales');
  });
});
