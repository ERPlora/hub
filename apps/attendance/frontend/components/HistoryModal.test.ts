// ATTENDANCE-F09 (who changed a working day, when and why): «History» on a row opens «Correction history»
// with every correction, newest first — who (or «System»), when, «Before» → «After» and the «Reason» —,
// or «This working day has never been corrected.». It reads `attendance.correction.list` when it opens;
// nothing in it can be edited.
import { describe, expect, it, vi } from 'vitest';

import { click, mountAttendance, settle } from '../__tests__/mount-attendance';
import type { CorrectionOut, RecordOut } from '../operations';
import HistoryModal from './HistoryModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const DAY = { id: 'r1', member_name: 'Bea Ruiz', work_date: '2026-10-05', status: 'closed' } as RecordOut;

const TRAIL: CorrectionOut[] = [
  {
    id: 'c2',
    record_id: 'r1',
    old_clock_in_at: '2026-10-05T07:00:00Z',
    old_clock_out_at: null,
    old_status: 'needs_review',
    new_clock_in_at: '2026-10-05T07:00:00Z',
    new_clock_out_at: '2026-10-05T15:00:00Z',
    new_status: 'closed',
    reason: 'Forgot to clock out',
    is_system: false,
    created_by_name: 'Marta Jefa',
    created_at: '2026-10-06T08:00:00Z',
  },
  {
    id: 'c1',
    record_id: 'r1',
    old_clock_in_at: '2026-10-05T06:00:00Z',
    old_clock_out_at: null,
    old_status: 'open',
    new_clock_in_at: '2026-10-05T07:00:00Z',
    new_clock_out_at: null,
    new_status: 'open',
    reason: 'Jornada cerrada al dar de baja a la persona en Personal.',
    is_system: true,
    created_by_name: '',
    created_at: '2026-10-05T09:00:00Z',
  },
];

async function setup(answer: [number, unknown], locale: 'en' | 'es' = 'en') {
  const m = await mountAttendance(HistoryModal, {
    props: { open: false, record: DAY },
    locale,
    path: '/attendance/records',
    answers: { '/api/attendance/corrections': answer },
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  await settle();
  return m;
}

describe('HistoryModal (ATTENDANCE-F09)', () => {
  it('asks for the history of the day when it opens and lists it newest first', async () => {
    const s = await setup([200, { rows: TRAIL, total: 2, limit: 100, offset: 0 }]);
    expect(s.sent()).toEqual([{ method: 'GET', path: '/api/attendance/corrections', query: { record_id: 'r1', limit: '100' }, body: undefined }]);
    expect(s.inDoc('attendance-history')?.getAttribute('aria-label')).toBe('Correction history');
    const items = [...(s.inDoc('attendance-history-list')?.querySelectorAll('[data-testid="attendance-history-item"]') ?? [])].map((li) => li.textContent?.replace(/\s+/g, ' ').trim());
    expect(items).toHaveLength(2);
    expect(items[0]).toContain('Marta Jefa · 2026-10-06 10:00');
    expect(items[0]).toContain('Before: 2026-10-05 09:00 → — (Needs review)');
    expect(items[0]).toContain('After: 2026-10-05 09:00 → 2026-10-05 17:00 (Closed)');
    expect(items[0]).toContain('Reason: Forgot to clock out');
    expect(items[1]).toContain('System');
  });

  it('a day never corrected says so', async () => {
    const s = await setup([200, { rows: [], total: 0, limit: 100, offset: 0 }]);
    expect(s.inDoc('attendance-history-empty')?.textContent).toContain('This working day has never been corrected.');
  });

  it('a failure says so', async () => {
    const s = await setup([500, { error: { code: 'error', message: 'Boom' } }]);
    expect(s.inDoc('attendance-history-load-error')?.textContent).toContain('The history could not be loaded.');
  });

  it('only closes', async () => {
    const s = await setup([200, { rows: [], total: 0, limit: 100, offset: 0 }]);
    expect(s.inDoc('attendance-history-submit')).toBeNull();
    await click(s.inDoc('attendance-history-close-button'));
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('speaks Spanish', async () => {
    const s = await setup([200, { rows: TRAIL, total: 2, limit: 100, offset: 0 }], 'es');
    const first = s.inDoc('attendance-history-list')?.textContent?.replace(/\s+/g, ' ') ?? '';
    expect(first).toContain('Antes:');
    expect(first).toContain('(Por revisar)');
    expect(first).toContain('Sistema');
  });
});
