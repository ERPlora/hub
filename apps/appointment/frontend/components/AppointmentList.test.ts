// The agenda's «List» (WORKBOOK «Agenda»): Time, No., Customer, Service, Professional and Status, «Search
// no., customer or service…», and per row Charge, Edit, Confirm, Start, Complete, No-show, Cancel, History
// and Delete — the one that does not apply greyed out, never hidden; Delete only for who may delete.
import { DataTable } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import type { AppointmentRow } from '../operations';
import { mountAppointment } from '../__tests__/mount-appointment';
import AppointmentList from './AppointmentList.vue';

const NOW = new Date('2026-10-19T12:00:00+02:00');
const row = (id: string, over: Partial<AppointmentRow> = {}): AppointmentRow => ({
  id,
  number: `APT-20261019-000${id}`,
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  start: '2026-10-19T10:00:00+02:00',
  end: '2026-10-19T10:30:00+02:00',
  duration_minutes: 30,
  status: 'confirmed',
  source: 'counter',
  services: [],
  service_names: 'Haircut, Colour',
  total: 6500,
  booked_by_customer: false,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
  ...over,
});

async function setup(props: Record<string, unknown> = {}) {
  const rows = [row('1'), row('2', { status: 'cancelled', customer_name: '', staff_id: null, staff_name: 'Ana López' }), row('3', { status: 'completed', sale_id: 's9' })];
  const m = await mountAppointment(AppointmentList, { props: { rows, now: NOW, canAdd: true, canDelete: true, ...props } });
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const actions = () => prop<Array<{ id: string; disabled?: (r: AppointmentRow) => boolean }>>('actions');
  const enabled = (item: AppointmentRow) => actions().filter((a) => !a.disabled?.(item)).map((a) => a.id);
  const cells = (i: number) => m.wrapper.findAll('[data-testid="appointment-list-row"]')[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, actions, enabled, cells, rows };
}

describe('AppointmentList', () => {
  it('paints the old columns, an erased customer and an unassigned row', async () => {
    const s = await setup();
    expect(s.cells(0).slice(0, 6)).toEqual(['10:00 AM', 'APT-20261019-0001', 'Lucía Pérez', 'Haircut, Colour', 'Ana López', 'Confirmed']);
    expect(s.cells(1).slice(2, 5)).toEqual(['Deleted customer', 'Haircut, Colour', 'Unassigned']);
    expect(s.cells(2)[5]).toContain('Charged');
    expect(s.prop('searchKeys')).toEqual(['number', 'customer_name', 'service_names', 'staff_name']);
    expect(s.prop('searchPlaceholder')).toBe('Search no., customer or service…');
  });

  it('greys out what a row does not allow, and Delete only exists for who may delete', async () => {
    const s = await setup();
    expect(s.actions().map((a) => a.id)).toEqual(['charge', 'edit', 'confirm', 'start', 'complete', 'no_show', 'cancel', 'history', 'delete']);
    expect(s.enabled(s.rows[0])).toEqual(['charge', 'edit', 'start', 'complete', 'no_show', 'cancel', 'history', 'delete']);
    expect(s.enabled(s.rows[2])).toEqual(['history']);
    const employee = await setup({ canDelete: false });
    expect(employee.actions().map((a) => a.id)).not.toContain('delete');
  });

  it('«Charge» becomes «Go to the check» while its check is open in the till', async () => {
    const s = await setup();
    const charge = s.actions().find((a) => a.id === 'charge') as unknown as { label: (r: AppointmentRow) => string };
    expect(charge.label(s.rows[0])).toBe('Charge');
    expect(charge.label(row('4', { order_id: 'o1' }))).toBe('Go to the check');
  });

  it('passes the row actions and «Add appointment» on', async () => {
    const s = await setup();
    s.table().vm.$emit('action', { actionId: 'confirm', row: s.rows[0] });
    s.table().vm.$emit('add');
    expect(s.wrapper.emitted('action')).toEqual([[{ actionId: 'confirm', row: s.rows[0] }]]);
    expect(s.wrapper.emitted('add')).toHaveLength(1);
    expect(s.prop('addable')).toBe(true);
  });
});
