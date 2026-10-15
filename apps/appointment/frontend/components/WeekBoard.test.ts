// APPOINTMENT-F27 «Ver la agenda de la semana»: «By professional · Week», a row per professional and a
// column per day, Monday to Sunday, each day's appointments in order (time, customer, services). Tapping
// an appointment opens it; tapping a day books on it with that professional; dragging an appointment to
// another day or row moves it keeping its time (never into the past).
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AppointmentRow, LaneOut } from '../operations';
import { click, mountAppointment, settle } from '../__tests__/mount-appointment';
import WeekBoard from './WeekBoard.vue';

const DAYS = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-24', '2026-10-25'];
const LANES: LaneOut[] = [
  { staff_id: 's1', name: 'Ana López', color: '', takes_bookings: true },
  { staff_id: 's2', name: 'Bea Ruiz', color: '', takes_bookings: true },
];
const row = (id: string, staff: string, day: string, time: string, over: Partial<AppointmentRow> = {}): AppointmentRow => ({
  id,
  number: `APT-${id}`,
  customer_id: 'c1',
  customer_name: `Customer ${id}`,
  staff_id: staff,
  staff_name: '',
  start: `${day}T${time}:00+02:00`,
  end: `${day}T${time}:00+02:00`,
  duration_minutes: 30,
  status: 'confirmed',
  source: 'counter',
  services: [],
  service_names: 'Haircut',
  total: 2000,
  booked_by_customer: false,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
  ...over,
});

afterEach(() => vi.restoreAllMocks());

async function setup(appointments: AppointmentRow[], props: Record<string, unknown> = {}) {
  const m = await mountAppointment(WeekBoard, {
    props: { days: DAYS, lanes: LANES, appointments, now: new Date('2026-10-19T08:00:00+02:00'), canBook: true, canMove: true, ...props },
  });
  const cell = (lane: string, day: string) => m.wrapper.find(`[data-testid="appointment-week-cell"][data-lane="${lane}"][data-day="${day}"]`);
  const chip = (id: string) => m.wrapper.find(`[data-testid="appointment-week-chip"][data-id="${id}"]`);
  const pointer = async (el: Element, type: string, x: number, y: number) => {
    el.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerId: 1, pointerType: 'mouse' }));
    await settle();
  };
  return { ...m, cell, chip, pointer };
}

describe('WeekBoard', () => {
  it('a column per day and a row per professional, each day’s appointments in order', async () => {
    const s = await setup([row('b', 's1', '2026-10-21', '12:00'), row('a', 's1', '2026-10-21', '09:30'), row('c', 's2', '2026-10-25', '10:00')]);
    const heads = s.wrapper.findAll('[data-testid="appointment-week-day"]').map((d) => d.text());
    // The reader's language decides the order of «Mon» and «19» (ICU).
    expect(heads.map((head) => head.replace(/\d+/, '').trim())).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
    expect(heads.map((head) => Number(head.match(/\d+/)?.[0]))).toEqual([19, 20, 21, 22, 23, 24, 25]);
    expect(s.cell('s1', '2026-10-21').findAll('[data-testid="appointment-week-chip"]').map((c) => c.text())).toEqual([
      expect.stringContaining('9:30 AM Customer a'),
      expect.stringContaining('12:00 PM Customer b'),
    ]);
    expect(s.cell('s2', '2026-10-25').text()).toContain('Customer c');
  });

  it('tapping an appointment opens it, and tapping a day books on it', async () => {
    const item = row('a', 's1', '2026-10-21', '09:30');
    const s = await setup([item]);
    await click(s.chip('a').element);
    await click(s.cell('s2', '2026-10-22').find('[data-testid="appointment-week-book"]').element);
    expect(s.wrapper.emitted('open')).toEqual([[item]]);
    expect(s.wrapper.emitted('slot')).toEqual([[{ staffId: 's2', staffName: 'Bea Ruiz', day: '2026-10-22' }]]);
  });

  it('dragging an appointment to another day and row moves it keeping its time', async () => {
    const item = row('a', 's1', '2026-10-21', '09:30');
    const s = await setup([item]);
    const target = s.cell('s2', '2026-10-23').element;
    vi.spyOn(document, 'elementFromPoint').mockReturnValue(target);
    const el = s.chip('a').element;
    await s.pointer(el, 'pointerdown', 10, 10);
    await s.pointer(el, 'pointermove', 200, 80);
    await s.pointer(el, 'pointerup', 200, 80);
    expect(s.wrapper.emitted('move')).toEqual([[{ row: item, staffId: 's2', day: '2026-10-23' }]]);
  });

  it('nothing is dropped into the past', async () => {
    const item = row('a', 's1', '2026-10-21', '07:00');
    const s = await setup([item], { now: new Date('2026-10-20T12:00:00+02:00') });
    vi.spyOn(document, 'elementFromPoint').mockReturnValue(s.cell('s1', '2026-10-19').element);
    const el = s.chip('a').element;
    await s.pointer(el, 'pointerdown', 10, 10);
    await s.pointer(el, 'pointermove', 200, 10);
    await s.pointer(el, 'pointerup', 200, 10);
    expect(s.wrapper.emitted('move')).toBeUndefined();
  });
});
