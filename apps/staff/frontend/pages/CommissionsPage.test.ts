// Staff → Commissions (WORKBOOK «Pantallas · Comisiones»; STAFF-F21 step 3): what each professional sold
// in a period (refunds taken off) and the commission it earns them, from the live
// `staff.commission.report`. The period is «Today» to begin with, then Yesterday, This week, This month or
// a range of one's own (prefilled with the period on screen); the server counts it in business days and
// judges the range (its 422 goes under «To»). Above the list, what the period sold and its commissions;
// a professional who no longer works here but sold in the period is marked. Only whoever sees the pay
// reads it; a business without Sales is told why there is nothing to show.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, errorFrame, type MountOptions, mountStaff } from '../__tests__/mount-staff';
import type { CommissionReportOut } from '../operations';
import CommissionsPage from './CommissionsPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

const OP = 'staff.commission.report';
const REPORT: CommissionReportOut = {
  date_from: '2026-08-19',
  date_to: '2026-08-19',
  sales_available: true,
  rows: [
    { member_id: 'm1', full_name: 'Ana López', role_name: 'Stylist', status: 'active', commission_rate: '15.00', sold: 2721, commission: 408 },
    { member_id: 'm2', full_name: 'Bea Ruiz', role_name: null, status: 'on_leave', commission_rate: '0.00', sold: 0, commission: 0 },
    { member_id: 'm3', full_name: 'Dora Gil', role_name: 'Barber', status: 'terminated', commission_rate: '12.50', sold: 1012, commission: 127 },
  ],
  total_sold: 3733,
  total_commission: 535,
};

type Control = HTMLElement & { value?: unknown; label?: string; errorText?: string; fill?: string };

const CHOICES = ['today', 'yesterday', 'this_week', 'this_month', 'custom'];

async function setup(options: MountOptions = {}, live = true) {
  const m = await mountStaff(CommissionsPage, { path: '/staff/commissions', ...options });
  if (live) await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="staff-commissions-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const control = (testid: string) => m.find(testid).element as Control;
  /** What a period button says (Ionic renders its label inside). */
  const chip = (value: string) =>
    m.find(`staff-commissions-period-${value}`).element.innerHTML.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  async function pick(value: string): Promise<void> {
    const segment = m.find('staff-commissions-period').element;
    (segment as Control).value = value;
    segment.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true }));
    await m.reopen();
  }
  async function type(testid: string, value: string): Promise<void> {
    const input = m.find(testid).element as Control;
    input.value = value;
    input.dispatchEvent(new CustomEvent('ionInput', { detail: { value }, bubbles: true }));
    await m.reopen();
  }
  return { ...m, table, prop, rows, cells, control, chip, pick, type, report: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('CommissionsPage', () => {
  it('follows today to begin with and paints each one: name, role, sold, rate and commission', async () => {
    // flow: STAFF-F21 (paso 3: la comisión del día)
    const s = await setup();
    expect(s.report()).toEqual([{ period: 'today' }]);
    await s.show(REPORT);
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['full_name', 'Name'],
      ['role_name', 'Role'],
      ['sold', 'Sold'],
      ['commission_rate', 'Commission %'],
      ['commission', 'Commission'],
    ]);
    expect(s.cells(0)).toEqual(['Ana López', 'Stylist', '€27.21', '15 %', '€4.08']);
    expect(s.cells(1)).toEqual(['Bea Ruiz', '—', '€0.00', '0 %', '€0.00']);
    expect(s.cells(2)[0]).toContain('Dora Gil');
    expect(s.cells(2)[0]).toContain('No longer works here');
    expect(s.cells(2).slice(1)).toEqual(['Barber', '€10.12', '12.5 %', '€1.27']);
    expect(s.wrapper.findAll('[data-testid="staff-commissions-left"]')).toHaveLength(1);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Staff');
    expect((s.wrapper.findComponent(AppPage).props('tabs') ?? []).map((t: { id: string }) => t.id)).toContain('commissions');
  });

  it('someone deactivated who sold in the period is marked «Inactive»', async () => {
    const s = await setup();
    const eva = { member_id: 'm4', full_name: 'Eva Sanz', role_name: null, status: 'inactive' as const, commission_rate: '10.00', sold: 500, commission: 50 };
    await s.show({ ...REPORT, rows: [eva], total_sold: 500, total_commission: 50 });
    expect(s.cells(0)[0]).toContain('Inactive');
    expect(s.find('staff-commissions-left').exists()).toBe(false);
  });

  it('on a phone, where each one is a card, the card title carries the mark too', async () => {
    const s = await setup();
    await s.show(REPORT);
    const title = s.prop<(row: unknown) => string>('cardTitle');
    expect(REPORT.rows.map((row) => title(row))).toEqual(['Ana López', 'Bea Ruiz', 'Dora Gil · No longer works here']);
    expect(title({ ...REPORT.rows[0], status: 'inactive' })).toBe('Ana López · Inactive');
  });

  it('above the list, what the period sold and its commissions, and the days it counts', async () => {
    const s = await setup();
    expect(s.find('staff-commissions-total-sold').text()).toContain('…');
    await s.show({ ...REPORT, date_from: '2026-08-17' });
    expect(s.find('staff-commissions-total-sold').text()).toMatch(/^Sold\s*€37\.33$/);
    expect(s.find('staff-commissions-total-commission').text()).toMatch(/^Commissions\s*€5\.35$/);
    expect(s.find('staff-commissions-days').text()).toBe('08/17/2026 – 08/19/2026');
    await s.result(OP, REPORT, {}, 2);
    expect(s.find('staff-commissions-days').text()).toBe('08/19/2026');
  });

  it('Yesterday, This week and This month change what it follows; the server counts them', async () => {
    const s = await setup();
    await s.show(REPORT);
    expect((s.control('staff-commissions-period') as Control).value).toBe('today');
    expect(CHOICES.map((value) => s.chip(value))).toEqual(['Today', 'Yesterday', 'This week', 'This month', 'Custom']);
    await s.pick('this_week');
    expect(s.report()).toEqual([{ period: 'this_week' }]);
    await s.pick('yesterday');
    expect(s.report()).toEqual([{ period: 'yesterday' }]);
  });

  it('Custom: «From» and «To», prefilled with the days on screen; each change goes to the server', async () => {
    const s = await setup();
    await s.show({ ...REPORT, date_from: '2026-08-17' });
    expect(s.find('staff-commissions-from').exists()).toBe(false);
    await s.pick('custom');
    const from = s.control('staff-commissions-from');
    expect([from.label, from.value, from.getAttribute('mode'), from.fill]).toEqual(['From', '2026-08-17', 'md', 'outline']);
    expect([s.control('staff-commissions-to').label, s.control('staff-commissions-to').value]).toEqual(['To', '2026-08-19']);
    expect(s.report()).toEqual([{ date_from: '2026-08-17', date_to: '2026-08-19' }]);
    await s.type('staff-commissions-from', '2026-08-01');
    expect(s.report()).toEqual([{ date_from: '2026-08-01', date_to: '2026-08-19' }]);
    await s.pick('this_month');
    expect(s.report()).toEqual([{ period: 'this_month' }]);
    expect(s.find('staff-commissions-from').exists()).toBe(false);
  });

  it('a «To» before «From»: the server’s word goes under «To» and the list waits', async () => {
    const s = await setup();
    await s.show(REPORT);
    await s.pick('custom');
    await s.type('staff-commissions-to', '2026-08-01');
    const error = { code: 'invalid_payload', message: 'Invalid parameters.', fields: { date_to: 'The end date cannot be before the start date.' } };
    s.net.lastStream().push(`event: error\ndata: ${JSON.stringify({ id: s.subId(OP), error })}\n\n`);
    await s.reopen();
    expect(s.control('staff-commissions-to').errorText).toBe('The end date cannot be before the start date.');
    expect(s.prop('error')).toBeUndefined();
  });

  it('nobody on the team can earn a commission yet: says so', async () => {
    const s = await setup();
    await s.show({ ...REPORT, rows: [], total_sold: 0, total_commission: 0 });
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No one on the team can earn a commission yet.');
  });

  it('loading, then a failure the list says with «Retry»', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await s.reopen();
    expect(s.prop('error')).toBe('msg boom');
    expect(s.prop<{ retry: string }>('labels').retry).toBe('Retry');
  });

  it('a business without Sales: commissions come from the sales, and no list', async () => {
    const s = await setup();
    await s.show({ ...REPORT, sales_available: false, rows: [], total_sold: 0, total_commission: 0 });
    expect(s.find('staff-commissions-no-sales').text()).toContain('Commissions come from the sales');
    expect(s.find('staff-commissions-no-sales').text()).toContain('Turn on Sales to see what each professional earned.');
    expect(s.table().exists()).toBe(false);
    expect(s.find('staff-commissions-total-sold').exists()).toBe(false);
  });

  it('an employee does not see the pay: «You do not have permission», and nothing followed', async () => {
    const s = await setup({ session: EMPLOYEE }, false);
    expect(s.find('staff-commissions-forbidden').text()).toContain('You do not have permission');
    expect(s.report()).toEqual([]);
    expect(s.table().exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(REPORT);
    expect(CHOICES.map((value) => s.chip(value))).toEqual(['Hoy', 'Ayer', 'Esta semana', 'Este mes', 'Personalizado']);
    expect(s.find('staff-commissions-total-sold').text()).toMatch(/^Vendido\s*37,33\s€$/);
    expect(s.find('staff-commissions-total-commission').text()).toMatch(/^Comisiones\s*5,35\s€$/);
    expect(s.find('staff-commissions-days').text()).toBe('19/08/2026');
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Nombre', 'Rol', 'Vendido', 'Comisión %', 'Comisión']);
    // Intl puts a no-break space before the euro sign.
    expect(s.cells(0).slice(2)).toEqual(['27,21\u00a0€', '15 %', '4,08\u00a0€']);
    expect(s.cells(2)[0]).toContain('Ya no trabaja aquí');
  });
});

describe('CommissionsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them', async () => {
    const s = await setup();
    await s.show(REPORT);
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
