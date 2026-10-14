// STAFF-F06 «Dar de baja a un profesional»: «Terminate» on a row asks first, as the old alert did:
// «Terminate {name}? …», «Last day (today if empty)» and «Reason (optional)» (up to 500), and the red
// «Terminate». It sends `staff.member.terminate` with the day only when one is given; a refusal stays
// in the dialog.
import { describe, expect, it, vi } from 'vitest';

import type { MemberOut } from '../operations';
import { click, ionValue, mountStaff, settle } from '../__tests__/mount-staff';
import TerminateDialog from './TerminateDialog.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; type?: string; disabled?: boolean; color?: string; errorText?: string };

const MEMBER = { id: 'm1', full_name: 'Ana López' } as MemberOut;

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountStaff(TerminateDialog, { props: { open: false, member: MEMBER }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const date = () => m.inDoc('staff-member-terminate-termination_date') as Control;
  const reason = () => m.inDoc('staff-member-terminate-reason') as Control;
  const confirm = () => m.inDoc('staff-member-terminate-submit') as Control;
  return { ...m, date, reason, confirm };
}

describe('TerminateDialog (STAFF-F06)', () => {
  it('names the person and asks for the last day and the reason, both optional', async () => {
    const s = await setup();
    expect(s.inDoc('staff-member-terminate')?.getAttribute('aria-label')).toBe('Terminate member');
    expect(s.inDoc('staff-member-terminate-message')?.textContent).toContain('Terminate Ana López?');
    expect([s.date().label, s.date().type, s.reason().label]).toEqual(['Last day (today if empty)', 'date', 'Reason (optional)']);
    expect([s.confirm().textContent?.trim(), s.confirm().disabled, s.confirm().color]).toEqual(['Terminate', false, 'danger']);
  });

  it('sends staff.member.terminate without a day when none is given (today, on the server), then closes', async () => {
    const s = await setup();
    s.answer(200, { id: 'm1', termination_date: '2026-10-14' });
    await ionValue(s.reason(), 'Moves abroad', 'ionInput');
    await click(s.confirm());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/staff/members/terminate', query: {}, body: { id: 'm1', reason: 'Moves abroad' } }]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('sends the last day when one is given', async () => {
    const s = await setup();
    s.answer(200, { id: 'm1', termination_date: '2026-10-31' });
    await ionValue(s.date(), '2026-10-31', 'ionInput');
    await click(s.confirm());
    expect(s.sent()[0].body).toEqual({ id: 'm1', termination_date: '2026-10-31', reason: '' });
  });

  it('a refusal stays in the dialog', async () => {
    const s = await setup();
    s.answer(404, { error: { code: 'not_found', message: 'That staff member does not exist in this business.' } });
    await click(s.confirm());
    expect(s.inDoc('staff-member-terminate-error')?.textContent).toContain('That staff member does not exist in this business.');
    expect(s.wrapper.emitted('update:open')?.at(-1)).not.toEqual([false]);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('staff-member-terminate')?.getAttribute('aria-label')).toBe('Dar de baja');
    expect([s.date().label, s.reason().label, s.confirm().textContent?.trim()]).toEqual([
      'Último día (hoy si se deja vacío)',
      'Motivo (opcional)',
      'Dar de baja',
    ]);
  });
});
