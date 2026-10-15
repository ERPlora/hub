// SERVICE-F17 «Anular un bono vendido por error»: «Void this voucher?» says whose voucher and for how
// much, that it stays as voided and that the money is refunded in Sales; the Reason is required (Void
// stays off without it); Void sends `service.grant.void` and closes; a refusal stays in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountService, settle } from '../__tests__/mount-service';
import { grant } from '../__tests__/grant';
import GrantVoidModal from './GrantVoidModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; disabled?: boolean; helperText?: string };

async function setup(over = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountService(GrantVoidModal, { props: { open: false, grant: grant({ used: 0, can_void: true, ...over }) }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  return { ...m, el: (id: string) => m.inDoc(id) as Control };
}

describe('GrantVoidModal', () => {
  it('says whose voucher and for how much, and that the money is refunded in Sales', async () => {
    const s = await setup();
    expect(s.inDoc('service-grant-void')?.getAttribute('aria-label')).toBe('Void this voucher?');
    expect(s.el('service-grant-void-message')?.textContent).toContain(
      'The voucher of customer Lucía Pérez (€90.00) stops being usable and stays in the list as voided.',
    );
    expect([s.el('service-grant-void-reason').label, s.el('service-grant-void-reason').helperText]).toEqual([
      'Reason',
      'Required. It stays on the voucher\'s record, e.g. «sold to the wrong customer».',
    ]);
    expect(s.el('service-grant-void-submit').disabled).toBe(true);
  });

  it('voids with the reason and closes', async () => {
    const s = await setup();
    s.answer(200, grant({ status: 'voided' }));
    await ionValue(s.el('service-grant-void-reason'), ' sold twice ', 'ionInput');
    await click(s.el('service-grant-void-submit'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/service/grants/void', query: {}, body: { id: 'g1', reason: 'sold twice' } }]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a refusal stays in the dialog', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'service.grant_in_use', message: 'That voucher was already used: it cannot be voided.' } });
    await ionValue(s.el('service-grant-void-reason'), 'oops', 'ionInput');
    await click(s.el('service-grant-void-submit'));
    expect(s.inDoc('service-grant-void-error')?.textContent).toContain('That voucher was already used: it cannot be voided.');
  });

  it('names a customer whose card is gone by its reference', async () => {
    const s = await setup({ customer_name: null });
    expect(s.el('service-grant-void-message')?.textContent).toContain('The voucher of customer cust-1 (€90.00)');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.inDoc('service-grant-void')?.getAttribute('aria-label')).toBe('¿Anular este bono?');
    expect(s.el('service-grant-void-submit')?.textContent).toContain('Anular');
  });
});
