// ATTENDANCE-F08 (correct a working day with its reason): «Correct» on a row opens «Correct working day»
// with the clock-in and clock-out in business time (an empty clock-out reopens the day) and a mandatory
// reason. The screen checks first what it can (a clock-out after the clock-in, a reason of 3) and sends
// `attendance.record.correct`; an untouched time keeps the stored instant, a changed one goes as the
// business's wall clock. The server's refusal (an overlap, a second open day) stays in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { click, errorFrame, ionValue, mountAttendance, settle } from '../__tests__/mount-attendance';
import type { RecordOut } from '../operations';
import CorrectionModal from './CorrectionModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; type?: string; errorText?: string; disabled?: boolean };

const DAY: RecordOut = {
  id: 'r1',
  member_id: 'm1',
  member_name: 'Bea Ruiz',
  work_date: '2026-10-05',
  clock_in_at: '2026-10-05T07:02:41.123456Z',
  clock_out_at: '2026-10-05T15:05:03Z',
  status: 'closed',
  source: 'shared',
  in_distance_m: null,
  in_within_radius: null,
  out_distance_m: null,
  out_within_radius: null,
  note: '',
  break_count: 0,
  break_seconds: 0,
  worked_seconds: 28942,
  break_started_at: null,
  correction_count: 0,
  as_of: '2026-10-06T08:30:00Z',
};

async function setup(record: RecordOut = DAY, locale: 'en' | 'es' = 'en', timezone: string | null = 'Europe/Madrid') {
  const m = await mountAttendance(CorrectionModal, { props: { open: false, record, team: true }, locale, path: '/attendance/records' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.live();
  if (timezone) await m.result('base.business.get', { timezone });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`attendance-correct-${name}`) as Control;
  const save = () => m.inDoc('attendance-correct-submit') as Control;
  return { ...m, field, save };
}

describe('CorrectionModal (ATTENDANCE-F08)', () => {
  it("shows each time on the business's clock and keeps an untouched one to the second (hub#779)", async () => {
    const s = await setup(DAY, 'en', 'Atlantic/Canary');
    // 07:02 UTC is 08:02 in the Canaries in October (UTC+1), 09:02 in Madrid.
    expect([s.field('clock_in').value, s.field('clock_out').value]).toEqual(['2026-10-05T08:02', '2026-10-05T16:05']);
    s.answerBy({ '/api/attendance/records/correct': [200, DAY] });
    await ionValue(s.field('clock_out'), '2026-10-05T16:30', 'ionInput');
    await ionValue(s.field('reason'), 'Forgot to clock out', 'ionInput');
    await click(s.save());
    await settle();
    expect(s.sent()[0].body).toMatchObject({ clock_in_at: DAY.clock_in_at, clock_out_at: '2026-10-05T16:30' });
  });

  it('cannot be saved until the business says its zone: what is typed is read on its clock (hub#779)', async () => {
    const s = await setup(DAY, 'en', null);
    expect(s.save().disabled).toBe(true);
    await ionValue(s.field('reason'), 'Forgot to clock out', 'ionInput');
    await s.result('base.business.get', { timezone: 'Atlantic/Canary' });
    await settle();
    expect(s.save().disabled).toBe(false);
    // Filled again on the business's clock, and what was written stays.
    expect([s.field('clock_in').value, s.field('clock_out').value, s.field('reason').value]).toEqual([
      '2026-10-05T08:02',
      '2026-10-05T16:05',
      'Forgot to clock out',
    ]);
  });

  it('says why it cannot be saved when the zone cannot be read, and lets it go when it can (hub#779)', async () => {
    const s = await setup(DAY, 'en', null);
    expect(s.inDoc('attendance-correct-error')).toBeNull();
    s.net.lastStream().push(errorFrame(s.subId('base.business.get'), 'base.boom'));
    await settle();
    expect(s.save().disabled).toBe(true);
    expect(s.inDoc('attendance-correct-error')?.textContent).toContain("The business's time zone could not be read");
    await s.result('base.business.get', { timezone: 'Atlantic/Canary' });
    await settle();
    expect(s.save().disabled).toBe(false);
    expect(s.inDoc('attendance-correct-error')).toBeNull();
  });

  it('says it in Spanish too (hub#779)', async () => {
    const s = await setup(DAY, 'es', null);
    s.net.lastStream().push(errorFrame(s.subId('base.business.get'), 'base.boom'));
    await settle();
    expect(s.inDoc('attendance-correct-error')?.textContent).toContain('No se ha podido leer la zona horaria del negocio');
  });

  it('a time typed before the business says its zone stays as it was typed (hub#779)', async () => {
    const s = await setup(DAY, 'en', null);
    await ionValue(s.field('clock_out'), '2026-10-05T16:30', 'ionInput');
    await s.result('base.business.get', { timezone: 'Atlantic/Canary' });
    await settle();
    expect(s.field('clock_out').value).toBe('2026-10-05T16:30');
  });

  it('shows the day and its times in business time, with an empty reason', async () => {
    const s = await setup();
    expect(s.inDoc('attendance-correct')?.getAttribute('aria-label')).toBe('Correct working day');
    expect(s.inDoc('attendance-correct-day')?.textContent).toContain('Bea Ruiz');
    expect([s.field('clock_in').type, s.field('clock_in').value, s.field('clock_in').label]).toEqual(['datetime-local', '2026-10-05T09:02', 'Clock-in']);
    expect([s.field('clock_out').value, s.field('clock_out').label]).toEqual(['2026-10-05T17:05', 'Clock-out (empty = still open)']);
    expect(s.field('reason').value).toBe('');
    expect(s.save().textContent?.trim()).toBe('Save correction');
  });

  it('keeps the stored instant of an untouched time and sends a changed one as business time', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/records/correct': [200, { ...DAY, clock_out_at: '2026-10-05T14:30:00Z' }] });
    await ionValue(s.field('clock_out'), '2026-10-05T16:30', 'ionInput');
    await ionValue(s.field('reason'), '  Forgot to clock out ', 'ionInput');
    await click(s.save());
    await settle();
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/attendance/records/correct',
        query: {},
        body: { record_id: 'r1', clock_in_at: '2026-10-05T07:02:41.123456Z', clock_out_at: '2026-10-05T16:30', reason: 'Forgot to clock out' },
      },
    ]);
    expect(s.wrapper.emitted('corrected')).toHaveLength(1);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an empty clock-out reopens the day', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/records/correct': [200, { ...DAY, clock_out_at: null, status: 'open' }] });
    await ionValue(s.field('clock_out'), '', 'ionInput');
    await ionValue(s.field('reason'), 'Still working', 'ionInput');
    await click(s.save());
    await settle();
    expect((s.sent()[0].body as { clock_out_at: unknown }).clock_out_at).toBeNull();
  });

  it('checks before sending: a clock-out after the clock-in and a reason of at least 3', async () => {
    const s = await setup();
    await ionValue(s.field('clock_out'), '2026-10-05T08:00', 'ionInput');
    await ionValue(s.field('reason'), 'ab', 'ionInput');
    await click(s.save());
    await settle();
    expect(s.sent()).toEqual([]);
    expect(s.field('clock_out').errorText).toBe('The clock-out must be after the clock-in.');
    expect(s.field('reason').errorText).toBe('Write a reason of at least 3 characters.');
    await ionValue(s.field('clock_in'), '', 'ionInput');
    await click(s.save());
    await settle();
    expect(s.field('clock_in').errorText).toBe('Enter the clock-in date and time.');
  });

  it('the server’s refusal stays in the dialog', async () => {
    const s = await setup();
    s.answerBy({
      '/api/attendance/records/correct': [409, { error: { code: 'attendance.overlap', message: 'These hours overlap another working day of this person.' } }],
    });
    await ionValue(s.field('reason'), 'Moved', 'ionInput');
    await click(s.save());
    await settle();
    expect(s.inDoc('attendance-correct-error')?.textContent).toContain('These hours overlap another working day of this person.');
    expect(s.wrapper.emitted('corrected')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup(DAY, 'es');
    expect(s.field('clock_out').label).toBe('Salida (vacía = sigue abierta)');
    expect(s.save().textContent?.trim()).toBe('Guardar corrección');
  });
});

describe('CorrectionModal: fields refused with the same words (hub#888)', () => {
  // Each time and the reason refused by the server under their own keys (`clock_in_at`, `clock_out_at`, `reason`).
  const FIELD_OF: Record<string, string> = { clock_in_at: 'clock_in', clock_out_at: 'clock_out' };
  itTellsTheCorrectedFieldApart(['clock_in_at', 'clock_out_at', 'reason'], async (locale, refusal) => {
    const s = await setup(DAY, locale);
    await ionValue(s.field('reason'), 'Forgot to clock out', 'ionInput');
    s.answerBy({ '/api/attendance/records/correct': [422, refusal] });
    return { field: (key) => s.field(FIELD_OF[key] ?? key), send: () => click(s.save()), settle };
  }, 'clock_out_at');
});
