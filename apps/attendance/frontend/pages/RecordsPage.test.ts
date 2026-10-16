// Time clock → Records (WORKBOOK «Pantallas · Registros»; ATTENDANCE-F06, F07, F08, F09, F10, F11), the old
// `erp-attendance-records`: the working days of the chosen month in a server-side DataTable — Date,
// Person, Clock-in, Clock-out, Breaks (min), Worked, Status and Location —, with «Correct» and «History»
// on each row and «Export CSV» above. An employee sees only their own (no Person, no Correct); a manager
// sees the team, filters by Person (with a search), Month and Status, and «Clocked in now» on top.
import { DataTable } from '@erplora/ui/components';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, flush, type MountOptions, mountAttendance, page } from '../__tests__/mount-attendance';
import CorrectionModal from '../components/CorrectionModal.vue';
import HistoryModal from '../components/HistoryModal.vue';
import PresenceCard from '../components/PresenceCard.vue';
import type { RecordOut } from '../operations';
import RecordsPage from './RecordsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

const download = vi.hoisted(() => ({ saveCsv: vi.fn() }));
vi.mock('../lib/download', () => ({ saveCsv: download.saveCsv }));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'attendance.record.list';
const NOW = '2026-10-06T08:30:00Z';
const OCTOBER = { date_from: '2026-10-01', date_to: '2026-10-31' };

const record = (id: string, over: Partial<RecordOut> = {}): RecordOut => ({
  id,
  member_id: 'm1',
  member_name: 'Ana López',
  work_date: '2026-10-05',
  clock_in_at: '2026-10-05T07:02:41Z',
  clock_out_at: '2026-10-05T15:05:03Z',
  status: 'closed',
  source: 'shared',
  in_distance_m: null,
  in_within_radius: null,
  out_distance_m: null,
  out_within_radius: null,
  note: '',
  break_count: 1,
  break_seconds: 1800,
  worked_seconds: 27142,
  break_started_at: null,
  correction_count: 0,
  as_of: NOW,
  ...over,
});

const ROWS = [
  record('r2', {
    member_name: 'Bea Ruiz',
    work_date: '2026-10-06',
    clock_in_at: '2026-10-06T07:00:00Z',
    clock_out_at: null,
    status: 'open',
    break_seconds: 0,
    worked_seconds: 5400,
    in_within_radius: true,
  }),
  record('r1', { in_within_radius: true, out_within_radius: false }),
];

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
  vi.setSystemTime(new Date(NOW));
  download.saveCsv.mockReset();
});
afterEach(() => vi.useRealTimers());

async function setup(options: MountOptions = {}) {
  const m = await mountAttendance(RecordsPage, { path: '/attendance/records', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="attendance-records-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, rows, cells, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('RecordsPage for a manager (ATTENDANCE-F07)', () => {
  it('follows the team’s days of this month, newest first, 50 from the first', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ ...OCTOBER, sort: '-clock_in_at', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'attendance-records', total: 2 });
    expect(s.prop('searchPlaceholder')).toBe('Search person…');
    expect(s.wrapper.findComponent(PresenceCard).exists()).toBe(true);
  });

  it('paints Date, Person, Clock-in, Clock-out, Breaks, Worked, Status and Location', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['work_date', 'Date'],
      ['member_name', 'Person'],
      ['clock_in_at', 'Clock-in'],
      ['clock_out_at', 'Clock-out'],
      ['break_minutes', 'Breaks (min)'],
      ['worked', 'Worked'],
      ['status', 'Status'],
      ['location', 'Location'],
    ]);
    const closed = s.cells(1);
    expect(closed.slice(0, 7)).toEqual(['Mon, Oct 5', 'Ana López', '09:02', '17:05', '30', '7:32', 'Closed']);
    expect(s.rows()[1].find('[data-testid="attendance-records-location-in"]').attributes('aria-label')).toBe(
      'Clock-in inside the workplace radius',
    );
    expect(s.rows()[1].find('[data-testid="attendance-records-location-out"]').attributes('aria-label')).toBe(
      'Clock-out outside the workplace radius',
    );
    const open = s.cells(0);
    expect(open[3]).toBe('—');
    expect(open[5]).toContain('1:30');
    expect(open[5]).toContain('In progress');
    expect(open[6]).toBe('Open');
  });

  it('the worked time of an open day runs on by the minute', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    vi.advanceTimersByTime(60_000);
    await flush();
    expect(s.cells(0)[5]).toContain('1:31');
  });

  it('runs on the server’s clock, not the device’s (review of 2026-10-15, finding 8)', async () => {
    vi.setSystemTime(new Date('2026-10-06T08:20:00Z')); // ten minutes behind the server
    const s = await setup();
    await s.show(page(ROWS));
    vi.advanceTimersByTime(60_000);
    await flush();
    expect(s.cells(0)[5]).toContain('1:31');
  });

  it('filters by month, status, person and search', async () => {
    const s = await setup();
    const month = s.find('attendance-records-month');
    month.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: '2026-09' } }));
    await flush();
    expect(s.list()).toEqual([{ date_from: '2026-09-01', date_to: '2026-09-30', sort: '-clock_in_at', limit: 50, offset: 0 }]);
    s.table().vm.$emit('filtersChange', { status: 'needs_review' });
    await flush();
    expect(s.list()[0]).toMatchObject({ status: 'needs_review' });
    s.wrapper.findComponent({ name: 'Combo' }).vm.$emit('update:modelValue', { id: 'm7', label: 'Carlos Gil' });
    await flush();
    expect(s.list()[0]).toMatchObject({ member_id: 'm7', status: 'needs_review' });
    s.table().vm.$emit('update:search', 'bea');
    await flush();
    expect(s.list()[0]).toMatchObject({ search: 'bea', offset: 0 });
  });

  it('offers the four years the law keeps in «Month»', async () => {
    const s = await setup();
    const options = s.find('attendance-records-month').findAll('ion-select-option');
    expect(options).toHaveLength(49);
    expect(options[0].text()).toBe('October 2026');
  });

  it('«Correct» and «History» open their dialogs on the row', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/corrections': [200, page([])] });
    await s.show(page(ROWS));
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['correct', 'history']);
    s.table().vm.$emit('action', { actionId: 'correct', row: ROWS[1] });
    await flush();
    expect(s.wrapper.findComponent(CorrectionModal).props()).toMatchObject({ open: true, record: ROWS[1], team: true });
    s.table().vm.$emit('action', { actionId: 'history', row: ROWS[0] });
    await flush();
    expect(s.wrapper.findComponent(HistoryModal).props()).toMatchObject({ open: true, record: ROWS[0] });
  });

  it('a correction says so', async () => {
    const s = await setup();
    s.wrapper.findComponent(CorrectionModal).vm.$emit('corrected', ROWS[1]);
    await flush();
    expect(s.find('attendance-records-corrected').text()).toContain('Working day corrected.');
  });

  it('«Export CSV» asks the server for every row of the filter and saves the file', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/records/export': [200, { filename: 'attendance-2026-10.csv', content_type: 'text/csv', rows: 2, csv: 'date,user\r\n' }] });
    await s.find('attendance-export-csv').trigger('click');
    await flush();
    expect(s.sent()).toEqual([
      {
        method: 'GET',
        path: '/api/attendance/records/export',
        query: { date_from: '2026-10-01', date_to: '2026-10-31', sort: '-clock_in_at' },
        body: undefined,
      },
    ]);
    expect(download.saveCsv).toHaveBeenCalledWith('attendance-2026-10.csv', 'date,user\r\n');
  });

  it('an empty export still downloads the header and says so; a failure says so', async () => {
    const s = await setup();
    s.answerBy({ '/api/attendance/records/export': [200, { filename: 'attendance-2026-10.csv', content_type: 'text/csv', rows: 0, csv: 'date\r\n' }] });
    await s.find('attendance-export-csv').trigger('click');
    await flush();
    expect(download.saveCsv).toHaveBeenCalledTimes(1);
    expect(s.find('attendance-records-export-notice').text()).toContain('the file only has the header');
    s.answerBy({ '/api/attendance/records/export': [500, { error: { code: 'error', message: 'Boom' } }] });
    await s.find('attendance-export-csv').trigger('click');
    await flush();
    expect(s.find('attendance-records-export-notice').text()).toContain('The CSV could not be exported.');
  });

  it('a month without days says so', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.find('attendance-records-empty').text()).toContain('No working days this month.');
  });
});

describe('RecordsPage for an employee (ATTENDANCE-F06)', () => {
  it('shows their own days: no Person, no search, no «Clocked in now», no «Correct»', async () => {
    const s = await setup({ session: EMPLOYEE });
    expect(s.list()).toEqual([{ ...OCTOBER, sort: '-clock_in_at', limit: 50, offset: 0 }]);
    await s.show(page([ROWS[1]]));
    expect(s.prop<Array<{ key: string }>>('columns').map((c) => c.key)).not.toContain('member_name');
    expect(s.prop('searchable')).toBe(false);
    expect(s.wrapper.findComponent(PresenceCard).exists()).toBe(false);
    expect(s.find('attendance-records-person').exists()).toBe(false);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['history']);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ session: { ...EMPLOYEE, language: 'es' }, locale: 'es' });
    await s.show(page([ROWS[1]]));
    expect(s.cells(0).slice(0, 6)).toEqual(['lun, 5 oct', '09:02', '17:05', '30', '7:32', 'Cerrada']);
    expect(s.find('attendance-export-csv').text()).toContain('Exportar CSV');
  });
});

describe('RecordsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
