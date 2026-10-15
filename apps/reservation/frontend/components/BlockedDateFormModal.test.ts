// RESERVATION-F02: «Add blocked date» — the Date, the Reason and «Whole day» (on); off, From and Until.
// «Block date». A date already blocked at that time goes on top.
import { describe, expect, it, vi } from 'vitest';

import { click, ionChecked, ionValue, mountReservation, settle } from '../__tests__/mount-reservation';
import { blockedRow } from '../__tests__/rows';
import BlockedDateFormModal from './BlockedDateFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountReservation(BlockedDateFormModal, { props: { open: false, day: '2026-10-15' }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`reservation-blocked-form-${name}`) as Control | null;
  return { ...m, field, submit: () => m.inDoc('reservation-blocked-form-submit') as Control };
}

describe('BlockedDateFormModal', () => {
  it('blocks a whole day with its reason', async () => {
    const s = await setup();
    expect([s.field('date')?.label, s.field('reason')?.label, s.field('date')?.value]).toEqual(['Date', 'Reason', '2026-10-15']);
    expect(s.field('blocked_from')).toBeNull();
    await ionValue(s.field('date'), '2026-12-25', 'ionInput');
    await ionValue(s.field('reason'), 'Christmas', 'ionInput');
    s.answer(201, blockedRow());
    await click(s.submit());
    expect(s.sent().map((call) => call.body)).toEqual([{ date: '2026-12-25', reason: 'Christmas', is_full_day: true }]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('blocks only some hours of a day', async () => {
    const s = await setup();
    await ionChecked(s.field('is_full_day'), false);
    await ionValue(s.field('blocked_from'), '20:00', 'ionInput');
    await ionValue(s.field('blocked_until'), '22:00', 'ionInput');
    s.answer(201, blockedRow());
    await click(s.submit());
    expect(s.sent().at(-1)?.body).toEqual({ date: '2026-10-15', reason: '', is_full_day: false, blocked_from: '20:00', blocked_until: '22:00' });
  });

  it('says when the date is already blocked, and speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.submit().textContent).toContain('Bloquear fecha');
    const message = 'Esa fecha ya está bloqueada a esa hora.';
    s.answer(409, { error: { code: 'reservation.blocked_date_exists', message, fields: { date: message } } });
    await click(s.submit());
    expect(s.inDoc('reservation-blocked-form-error')?.textContent).toContain(message);
  });
});
