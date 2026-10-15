// The steps that ask first (RESERVATION-F09, F10, F20; the market: a confirmation naming whose booking
// and when): «Cancel reservation» with an optional reason, «Mark no-show» and «Delete for good». A
// refusal stays in the dialog; done, it closes and says which reservation changed.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountReservation, settle } from '../__tests__/mount-reservation';
import { reservationRow } from '../__tests__/rows';
import StepDialog from './StepDialog.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function setup(kind: 'cancel' | 'no_show' | 'delete', locale: 'en' | 'es' = 'en', row = reservationRow()) {
  const m = await mountReservation(StepDialog, { props: { open: false, kind, reservation: row }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  return m;
}

describe('StepDialog', () => {
  it('cancels naming whose reservation and when, with the reason', async () => {
    const s = await setup('cancel');
    const dialog = s.inDoc('reservation-step-cancel');
    expect(s.wrapper.html() + document.body.innerHTML).toContain('Cancel the reservation?');
    expect(dialog?.textContent).toContain('Ana García · Thursday, October 15 · 9:00 PM. Its place and its table are freed.');
    await ionValue(s.inDoc('reservation-step-cancel-reason'), 'Ill', 'ionInput');
    s.answer(200, reservationRow({ status: 'cancelled' }));
    await click(s.inDoc('reservation-step-cancel-submit'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/reservation/reservations/cancel', query: {}, body: { id: 'r1', reason: 'Ill' } },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    expect(s.wrapper.emitted('done')).toEqual([['cancel']]);
  });

  it('marks a no-show and deletes, each with its own words and route', async () => {
    const noShow = await setup('no_show');
    expect(noShow.inDoc('reservation-step-no_show-submit')?.textContent).toContain('Mark no-show');
    expect(noShow.inDoc('reservation-step-no_show-reason')).toBeNull();
    noShow.answer(200, reservationRow({ status: 'no_show' }));
    await click(noShow.inDoc('reservation-step-no_show-submit'));
    expect(noShow.sent()[0]).toMatchObject({ path: '/api/reservation/reservations/no_show', body: { id: 'r1' } });
    const gone = await setup('delete');
    expect(gone.inDoc('reservation-step-delete')?.textContent).toContain('It leaves the book for good');
    gone.answer(200, { id: 'r1' });
    await click(gone.inDoc('reservation-step-delete-submit'));
    expect(gone.sent()[0]).toMatchObject({ path: '/api/reservation/reservations/delete', body: { id: 'r1' } });
  });

  it('keeps a refusal in the dialog, says «Deleted customer» for an erased guest, and speaks Spanish', async () => {
    const s = await setup('cancel', 'es', reservationRow({ guest_name: '' }));
    expect(s.inDoc('reservation-step-cancel')?.textContent).toContain('Cliente borrado · Jueves, 15 de octubre · 21:00');
    expect(s.inDoc('reservation-step-cancel-cancel')?.textContent).toContain('Mantenerla');
    s.answer(409, { error: { code: 'reservation.illegal_transition', message: 'Esta reserva está sentada: no se puede cancelar.' } });
    await click(s.inDoc('reservation-step-cancel-submit'));
    expect(s.inDoc('reservation-step-cancel-error')?.textContent).toContain('no se puede cancelar');
    expect(s.wrapper.emitted('done')).toBeUndefined();
  });
});
