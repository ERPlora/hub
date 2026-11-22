// ATTENDANCE-F09 (who changed a working day, when and why): «History» on a row opens «Correction history»
// with every correction, newest first — who (or «System»), when, «Before» → «After» and the «Reason» —,
// or «This working day has never been corrected.». It reads `attendance.correction.list` when it opens;
// nothing in it can be edited.
import { describe, expect, it } from 'vitest';

import { click, mountAttendance, settle } from '../__tests__/mount-attendance';
import type { CorrectionOut, RecordOut } from '../operations';
import HistoryModal from './HistoryModal.vue';

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

async function setup(answer: [number, unknown], locale: 'en' | 'es' = 'en', timezone = 'Europe/Madrid') {
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
  await m.live();
  await m.result('base.business.get', { timezone });
  return m;
}

describe('HistoryModal (ATTENDANCE-F09)', () => {
  it("tells each correction on the business's clock (hub#779)", async () => {
    const s = await setup([200, { rows: TRAIL, total: 2, limit: 100, offset: 0 }], 'en', 'Atlantic/Canary');
    const item = s.inDoc('attendance-history-list')?.querySelector('[data-testid="attendance-history-item"]')?.textContent;
    expect(item).toContain('Marta Jefa · Tue, Oct 6 · 09:00');
    expect(item).toContain('Before: 08:00 → — (Needs review)');
    expect(item).toContain('After: 08:00 → 16:00 (Closed)');
  });

  it('asks for the history of the day when it opens and lists it newest first', async () => {
    const s = await setup([200, { rows: TRAIL, total: 2, limit: 100, offset: 0 }]);
    expect(s.sent()).toEqual([{ method: 'GET', path: '/api/attendance/corrections', query: { record_id: 'r1', limit: '100' }, body: undefined }]);
    expect(s.inDoc('attendance-history')?.getAttribute('aria-label')).toBe('Correction history');
    const items = [...(s.inDoc('attendance-history-list')?.querySelectorAll('[data-testid="attendance-history-item"]') ?? [])].map((li) => li.textContent?.replace(/\s+/g, ' ').trim());
    expect(items).toHaveLength(2);
    expect(items[0]).toContain('Marta Jefa · Tue, Oct 6 · 10:00');
    expect(items[0]).toContain('Before: 09:00 → — (Needs review)');
    expect(items[0]).toContain('After: 09:00 → 17:00 (Closed)');
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

  it('writes its dates and times as the rest of the screen does, in Spanish too (hub#2045)', async () => {
    const s = await setup([200, { rows: TRAIL, total: 2, limit: 100, offset: 0 }], 'es');
    const first = s.inDoc('attendance-history-list')?.querySelector('[data-testid="attendance-history-item"]')?.textContent?.replace(/\s+/g, ' ') ?? '';
    expect(first).toContain('Marta Jefa · mar, 6 oct · 10:00');
    expect(first).toContain('Antes: 09:00 → — (Por revisar)');
    expect(first).toContain('Después: 09:00 → 17:00 (Cerrada)');
    expect(first).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  });

  it('a time on another day than the working day says which (a night shift)', async () => {
    const night: CorrectionOut = { ...TRAIL[0], new_clock_out_at: '2026-10-06T01:30:00Z' };
    const s = await setup([200, { rows: [night], total: 1, limit: 100, offset: 0 }], 'es');
    const item = s.inDoc('attendance-history-list')?.querySelector('[data-testid="attendance-history-item"]')?.textContent?.replace(/\s+/g, ' ') ?? '';
    expect(item).toContain('Después: 09:00 → 03:30 (6/10) (Cerrada)');
  });
});
