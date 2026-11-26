// Tips → Report (TIP-F13; WORKBOOK «Pantallas · Informe»): the team's tips of the period — Today to begin with, 7 or
// 30 days — live, by person or by shift (`tip.report.get`): the period's figures above, and a line per person (the
// unassigned last) or per clocked working day (those outside every day last), with how many and how much by card, in
// cash and other ways; «Export» saves what is on screen as CSV. Every state of the screen: loading, empty, error,
// reconnecting, Time clock off by shift, the app off and a session without the permission.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { BYE, errorFrame, flush, tabsOf, words } from '../../../../base/frontend/__tests__/mount-in-shell';
import { EMPLOYEE, MANAGER, mountTip, onTheTwentyFifth } from '../__tests__/mount-tip';
import TipFigures from '../components/TipFigures.vue';
import type { ReportOut, ReportRowOut } from '../operations';
import ReportPage from './ReportPage.vue';

const download = vi.hoisted(() => ({ saveCsv: vi.fn(async () => true) }));
vi.mock('../../../../base/frontend/lib/download', () => download);

const OP = 'tip.report.get';
const TODAY = { date_from: '2026-11-25', date_to: '2026-11-25' };

const line = (member: string | null, fields: Partial<ReportRowOut> = {}): ReportRowOut => ({
  member_id: member,
  member_name: member ? `${member} Gil` : '',
  shift_id: null,
  clock_in_at: null,
  clock_out_at: null,
  card: 1000,
  cash: 250,
  other: 0,
  total: 1250,
  count: 3,
  ...fields,
});

const TOTALS = { card: 1000, cash: 1450, other: 0, total: 2450, count: 4 };
const BY_PERSON: ReportOut = {
  by: 'person',
  ...TODAY,
  shifts_available: true,
  rows: [line('Bea'), line(null, { card: 0, cash: 1200, total: 1200, count: 1 })],
  totals: TOTALS,
};
const BY_SHIFT: ReportOut = {
  ...BY_PERSON,
  by: 'shift',
  rows: [
    line('Bea', { shift_id: 's1', clock_in_at: '2026-11-25T08:00:00Z', clock_out_at: '2026-11-25T16:30:00Z' }),
    line(null, { card: 0, cash: 1200, total: 1200, count: 1 }),
  ],
};

onTheTwentyFifth();
beforeEach(() => download.saveCsv.mockClear());

async function setup(locale: 'en' | 'es' = 'en', session = MANAGER) {
  const m = await mountTip(ReportPage, { path: '/tip/report', locale, session });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const cells = (i: number) => m.wrapper.findAll('[data-testid="tip-report-row"]')[i].findAll('[role="cell"]').map((cell) => words(cell.element));
  const figures = () => m.wrapper.findComponent(TipFigures).props('figures');
  const show = (report: ReportOut) => m.result(OP, report);
  async function fail(code: string) {
    m.net.lastStream().push(errorFrame(m.subId(OP), code));
    await flush();
  }
  async function choose(testid: string, value: string) {
    m.find(testid).element.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
    await m.reopen();
  }
  return { ...m, table, prop, cells, figures, show, fail, choose };
}

describe('ReportPage: the report', () => {
  it('sits under «Tips», among the sections of whoever manages them', async () => {
    const { wrapper } = await setup();
    expect(wrapper.findComponent(AppPage).props('title')).toBe('Tips');
    expect(tabsOf(wrapper)).toEqual([
      ['tips', 'Tips'],
      ['report', 'Report'],
      ['settings', 'Settings'],
      ['mine', 'My tips'],
    ]);
  });

  it('follows today’s report by person, loading until the first result', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ by: 'person', ...TODAY }]);
    expect(s.prop('loading')).toBe(true);
    expect(s.prop<{ loading: string }>('labels').loading).toBe('Loading the report…');
    expect(s.figures()).toBeUndefined();
    await s.show(BY_PERSON);
    expect(s.prop('loading')).toBe(false);
  });

  it('paints the period’s figures and a line per person, the unassigned named so', async () => {
    const s = await setup();
    await s.show(BY_PERSON);
    expect(s.figures()).toEqual(TOTALS);
    expect(s.prop<Array<{ label: string }>>('columns').map((column) => column.label)).toEqual(['Person', 'Tips', 'By card', 'In cash', 'Other ways', 'Total']);
    expect(s.cells(0)).toEqual(['Bea Gil', '3', '€10.00', '€2.50', '€0.00', '€12.50']);
    expect(s.cells(1).slice(0, 2)).toEqual(['Unassigned', '1']);
    expect(s.table().props()).toMatchObject({ views: ['table', 'cards'], testid: 'tip-report' });
  });

  it('by shift, a line per working day with its clock-in and clock-out, those outside every day named so', async () => {
    const s = await setup();
    await s.choose('tip-report-by', 'shift');
    expect(s.params(OP)).toEqual([{ by: 'shift', ...TODAY }]);
    await s.show(BY_SHIFT);
    expect(s.prop<Array<{ label: string }>>('columns').map((column) => column.label)).toEqual(['Person', 'Working day', 'Tips', 'By card', 'In cash', 'Other ways', 'Total']);
    expect(s.cells(0).slice(0, 2)).toEqual(['Bea Gil', expect.stringMatching(/^Nov 25, 2026, \d+:00\sAM – \d+:30\sPM$/)]);
    expect(s.cells(1).slice(0, 2)).toEqual(['Outside a clocked working day', '—']);
  });

  it('counts the period back from today: 7 days, 30 days', async () => {
    const s = await setup();
    await s.choose('tip-report-period', 'week');
    expect(s.params(OP)).toEqual([{ by: 'person', date_from: '2026-11-19', date_to: '2026-11-25' }]);
    await s.choose('tip-report-period', 'month');
    expect(s.params(OP)).toEqual([{ by: 'person', date_from: '2026-10-27', date_to: '2026-11-25' }]);
  });

  it('by shift without Time clock says so in place of the lines, and keeps the figures and the way back by person', async () => {
    const s = await setup();
    await s.choose('tip-report-by', 'shift');
    await s.show({ ...BY_SHIFT, shifts_available: false, rows: [] });
    expect(s.find('tip-report-no-shifts').text()).toContain('Time clock is not active');
    expect(s.find('tip-report-empty').exists()).toBe(false);
    expect(s.figures()).toEqual(TOTALS);
    await s.choose('tip-report-by', 'person');
    expect(s.params(OP)).toEqual([{ by: 'person', ...TODAY }]);
  });

  it('says «No tips in this period.» with none', async () => {
    const s = await setup();
    await s.show({ ...BY_PERSON, rows: [], totals: { card: 0, cash: 0, other: 0, total: 0, count: 0 } });
    expect((s.wrapper.findComponent(EmptyState as unknown as Component).props() as Record<string, unknown>).heading).toBe('No tips in this period.');
  });

  it('while the stream reconnects keeps the lines and says «Reconnecting…»', async () => {
    const s = await setup();
    await s.show(BY_PERSON);
    s.net.lastStream().push(BYE);
    await flush();
    expect(s.find('tip-report-reconnecting').text()).toBe('Reconnecting…');
    expect(s.cells(0)[0]).toBe('Bea Gil');
  });

  it('a read that fails is the table’s error with Retry; the app off replaces the report', async () => {
    const s = await setup();
    await s.fail('tip.boom');
    expect([s.prop('error'), s.prop<{ loadError: string }>('labels').loadError]).toEqual(['msg tip.boom', 'The report could not be loaded.']);
    await s.fail('app_inactive');
    expect(s.find('tip-report-inactive').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
    expect(s.find('tip-report-export').exists()).toBe(false);
  });

  it('a session without the permission is told so, with no lines, figures nor export', async () => {
    const s = await setup('en', EMPLOYEE);
    await s.fail('permission_denied');
    expect(s.find('tip-report-forbidden').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
    expect(s.wrapper.findComponent(TipFigures).exists()).toBe(false);
    expect(s.find('tip-report-export').exists()).toBe(false);
  });
});

describe('ReportPage: Export', () => {
  it('saves the lines on screen as CSV, named after the view and the days', async () => {
    const s = await setup();
    const exportButton = () => s.find('tip-report-export').element as HTMLIonButtonElement;
    expect(exportButton().disabled).toBe(true);
    await s.show(BY_PERSON);
    expect(exportButton().disabled).toBe(false);
    await s.find('tip-report-export').trigger('click');
    await flush();
    expect(download.saveCsv).toHaveBeenCalledOnce();
    const [filename, csv] = download.saveCsv.mock.calls[0] as unknown as [string, string];
    expect(filename).toBe('tips-by-person-2026-11-25.csv');
    expect(csv.split('\r\n').slice(0, 3)).toEqual(['Person,Tips,By card,In cash,Other ways,Total', 'Bea Gil,3,10.00,2.50,0.00,12.50', 'Unassigned,1,0.00,12.00,0.00,12.00']);
  });
});

describe('ReportPage: in Spanish', () => {
  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.show(BY_PERSON);
    expect(s.prop<Array<{ label: string }>>('columns').map((column) => column.label)).toEqual(['Persona', 'Propinas', 'Con tarjeta', 'En efectivo', 'Otras formas', 'Total']);
    expect(s.cells(1)[0]).toBe('Sin asignar');
    const exportButton = s.find('tip-report-export');
    expect(exportButton.text()).toBe('');
    expect([exportButton.attributes('aria-label'), exportButton.attributes('title')]).toEqual(['Exportar', 'Exportar']);
  });
});
