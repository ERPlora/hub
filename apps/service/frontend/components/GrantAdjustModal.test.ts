// SERVICE-F18 «Regalar sesiones, alargar la caducidad o corregir el saldo»: «Adjust this voucher» adds
// or removes sessions (only with a limit; removing up to what is left) and/or extends the expiry (only
// when it expires; up to 366 days), with a required Reason and the preview of what is left after.
// Adjust sends `service.grant.adjust` with signed sessions and closes; a refusal stays in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountService, settle } from '../__tests__/mount-service';
import { grant } from '../__tests__/grant';
import GrantAdjustModal from './GrantAdjustModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; disabled?: boolean; helperText?: string; value?: unknown };

async function setup(over = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountService(GrantAdjustModal, { props: { open: false, grant: grant(over) }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  return { ...m, el: (id: string) => m.inDoc(id) as Control };
}

describe('GrantAdjustModal', () => {
  it('offers to add or remove sessions and to extend the expiry, with what is left now', async () => {
    const s = await setup();
    expect(s.inDoc('service-grant-adjust')?.getAttribute('aria-label')).toBe('Adjust this voucher');
    expect(s.el('service-grant-adjust-message')?.textContent).toContain('Give customer Lucía Pérez extra sessions');
    expect([s.el('service-grant-adjust-uses').label, s.el('service-grant-adjust-uses').helperText]).toEqual([
      'Sessions to add',
      '3 left now. Up to 100.',
    ]);
    expect([s.el('service-grant-adjust-days').label, s.el('service-grant-adjust-days').helperText]).toEqual([
      'Days to extend',
      'Expires Mar 30, 2027 now. Up to 366.',
    ]);
    expect(s.el('service-grant-adjust-submit').disabled).toBe(true);
  });

  it('gives sessions and days with a reason, previewing the balance after', async () => {
    const s = await setup();
    s.answer(200, grant({ remaining: 5 }));
    await ionValue(s.el('service-grant-adjust-uses'), '2', 'ionInput');
    await ionValue(s.el('service-grant-adjust-days'), '30', 'ionInput');
    await ionValue(s.el('service-grant-adjust-reason'), 'closed in August', 'ionInput');
    expect(s.el('service-grant-adjust-preview')?.textContent).toContain('After the adjustment: 5 session(s) left · expires Apr 29, 2027');
    await click(s.el('service-grant-adjust-submit'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/service/grants/adjust', query: {}, body: { id: 'g1', uses_delta: 2, days_delta: 30, reason: 'closed in August' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('removes sessions as a negative delta, up to what is left', async () => {
    const s = await setup();
    await ionValue(s.el('service-grant-adjust-direction'), 'remove', 'ionChange');
    expect([s.el('service-grant-adjust-uses').label, s.el('service-grant-adjust-uses').helperText]).toEqual([
      'Sessions to remove',
      '3 left now. You can remove up to 3.',
    ]);
    s.answer(200, grant({ remaining: 2 }));
    await ionValue(s.el('service-grant-adjust-uses'), '1', 'ionInput');
    await ionValue(s.el('service-grant-adjust-reason'), 'typo', 'ionInput');
    await click(s.el('service-grant-adjust-submit'));
    expect(s.sent()[0].body).toEqual({ id: 'g1', uses_delta: -1, days_delta: 0, reason: 'typo' });
  });

  it('an unlimited voucher only extends its expiry; one that never expires only moves sessions', async () => {
    const unlimited = await setup({ max_uses: null, remaining: null });
    expect([unlimited.el('service-grant-adjust-uses'), unlimited.el('service-grant-adjust-direction')]).toEqual([null, null]);
    expect(unlimited.el('service-grant-adjust-days')).not.toBeNull();
    const forever = await setup({ expires_at: null });
    expect(forever.el('service-grant-adjust-days')).toBeNull();
  });

  it('a refusal stays in the dialog', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'service.grant_adjust_below_used', message: 'You cannot take away more sessions than the customer has left.' } });
    await ionValue(s.el('service-grant-adjust-uses'), '1', 'ionInput');
    await ionValue(s.el('service-grant-adjust-reason'), 'x', 'ionInput');
    await click(s.el('service-grant-adjust-submit'));
    expect(s.inDoc('service-grant-adjust-error')?.textContent).toContain('You cannot take away more sessions than the customer has left.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.inDoc('service-grant-adjust')?.getAttribute('aria-label')).toBe('Ajustar este bono');
    expect(s.el('service-grant-adjust-uses').label).toBe('Sesiones que se añaden');
  });
});
