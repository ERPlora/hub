// What the agenda's row actions do (WORKBOOK «Agenda»; APPOINTMENT-F03 to F11, F17): Confirm, Start,
// Complete and No-show at once; Cancel and Delete ask first; History opens the history; Edit opens the
// panel; Charge opens the check in the till and goes there. Dragging a block moves it; an overlap asks
// «Book anyway» first. A refusal is told on the page, never swallowed.
import { describe, expect, it, vi } from 'vitest';

import type { AppointmentRow } from '../operations';
import { mountComposable, settle } from '../__tests__/mount-appointment';
import { type AgendaActions, useAgendaActions } from './useAgendaActions';

const ROW = { id: 'a1', number: 'APT-1', start: '2026-10-19T10:00:00+02:00', staff_id: 's1' } as AppointmentRow;

async function setup() {
  const onEdit = vi.fn();
  let actions!: AgendaActions;
  const m = await mountComposable(() => {
    actions = useAgendaActions({ onEdit });
  });
  return { ...m, actions: () => actions, onEdit };
}

describe('useAgendaActions', () => {
  it('confirms, starts, completes and marks a no-show at once', async () => {
    const s = await setup();
    s.answer(200, ROW);
    for (const action of ['confirm', 'start', 'complete', 'no_show']) await s.actions().run(action, ROW);
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/appointment/appointments/confirm', { id: 'a1' }],
      ['/api/appointment/appointments/start', { id: 'a1' }],
      ['/api/appointment/appointments/complete', { id: 'a1' }],
      ['/api/appointment/appointments/mark_no_show', { id: 'a1' }],
    ]);
  });

  it('tells a refusal on the page', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'appointment.cannot_confirm', message: 'It is not pending any more.' } });
    await s.actions().run('confirm', ROW);
    expect(s.actions().notice.value).toEqual({ tone: 'danger', text: 'It is not pending any more.' });
  });

  it('Cancel, Delete and History open their dialogs; Edit opens the panel', async () => {
    const s = await setup();
    await s.actions().run('cancel', ROW);
    expect([s.actions().cancelOpen.value, s.actions().target.value]).toEqual([true, ROW]);
    await s.actions().run('delete', ROW);
    expect(s.actions().deleteOpen.value).toBe(true);
    s.answer(200, { id: 'a1' });
    await s.actions().confirmDelete();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/appointment/appointments/delete', body: { id: 'a1' } });
    expect(s.actions().deleteOpen.value).toBe(false);
    await s.actions().run('history', ROW);
    expect(s.actions().historyOpen.value).toBe(true);
    await s.actions().run('edit', ROW);
    expect(s.onEdit).toHaveBeenCalledWith(ROW);
  });

  it('Charge opens the check in the till and the till shows it (its address names it)', async () => {
    const s = await setup();
    s.answer(200, { appointment_id: 'a1', order_id: 'o1', label: 'Lucía Pérez · APT-1' });
    await s.actions().run('charge', ROW);
    await settle();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/appointment/appointments/charge', body: { id: 'a1' } });
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos?order=o1');
    expect(s.actions().notice.value).toBeNull();
  });

  it('«Go to the check» goes back to the check already open', async () => {
    const s = await setup();
    s.answer(200, { appointment_id: 'a1', order_id: 'o1', label: 'Lucía Pérez · APT-1' });
    await s.actions().run('charge', { ...ROW, order_id: 'o1' });
    await settle();
    expect(s.sent().at(-1)).toMatchObject({ path: '/api/appointment/appointments/charge', body: { id: 'a1' } });
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos?order=o1');
  });

  it('a drag moves the appointment, asking first when it overlaps', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'appointment.overlap_needs_confirmation', message: 'Overlaps APT-2. Book it anyway?' } });
    await s.actions().move(ROW, { start: '2026-10-19T11:00', staffId: 's2' });
    expect(s.actions().overlap.value).toBe('Overlaps APT-2. Book it anyway?');
    s.answer(200, ROW);
    await s.actions().confirmOverlap();
    expect(s.sent().map((call) => call.body)).toEqual([
      { id: 'a1', start: '2026-10-19T11:00', staff_id: 's2', confirm_overlap: false },
      { id: 'a1', start: '2026-10-19T11:00', staff_id: 's2', confirm_overlap: true },
    ]);
    expect([s.actions().overlap.value, s.actions().notice.value?.text]).toEqual([null, 'Appointment moved.']);
  });
});
