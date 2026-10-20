// APPOINTMENT-F01, F04, F25: «By professional · Day», the old `ok-scheduler` timeline. A row per bookable
// professional, then whoever no longer takes bookings but keeps appointments that day (with the warning
// above), then «Unassigned» when an appointment has nobody; the calendar window's hours across. Tapping a
// free slot books there (with that professional and time; on a row that takes no bookings, only the time);
// tapping an appointment opens it; dragging one moves it to another time or row (the mouse at once, a
// finger after holding it), never into the past; the blocked periods are painted.
import { describe, expect, it } from 'vitest';

import type { AppointmentRow, BlockedTimeOut, LaneOut } from '../operations';
import type { DayHours } from './DayGrid.vue';
import { click, mountAppointment, settle } from '../__tests__/mount-appointment';
import DayGrid from './DayGrid.vue';

const NOW = new Date('2026-10-19T08:00:00+02:00');
const LANES: LaneOut[] = [
  { staff_id: 's1', name: 'Ana López', color: '#AA3300', takes_bookings: true },
  { staff_id: 's2', name: 'Bea Ruiz', color: '', takes_bookings: true },
  { staff_id: 's3', name: 'Carla Sanz', color: '', takes_bookings: false },
];
const row = (id: string, staff: string | null, start: string, minutes = 30, over: Partial<AppointmentRow> = {}): AppointmentRow => ({
  id,
  number: `APT-${id}`,
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: staff,
  staff_name: staff ? 'x' : 'Ana López',
  start: `2026-10-19T${start}:00+02:00`,
  end: `2026-10-19T${start}:00+02:00`,
  duration_minutes: minutes,
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
const BLOCK: BlockedTimeOut = {
  id: 'b1',
  title: 'Training',
  block_type: 'other',
  start: '2026-10-19T13:00:00+02:00',
  end: '2026-10-19T14:00:00+02:00',
  all_day: false,
  staff_id: null,
  staff_name: '',
  reason: '',
};

async function setup(appointments: AppointmentRow[] = [], props: Record<string, unknown> = {}) {
  const m = await mountAppointment(DayGrid, {
    props: {
      day: '2026-10-19',
      lanes: LANES,
      appointments,
      blocks: [BLOCK],
      startHour: 8,
      endHour: 20,
      slotInterval: 30,
      now: NOW,
      canBook: true,
      canMove: true,
      ...props,
    },
  });
  const lanes = () => m.wrapper.findAll('[data-testid="appointment-grid-lane"]').map((l) => l.attributes('data-lane'));
  const block = (id: string) => m.wrapper.find(`[data-testid="appointment-grid-appointment"][data-id="${id}"]`);
  const pointer = async (el: Element, type: string, x: number, y: number, pointerType = 'mouse') => {
    el.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerId: 1, pointerType }));
    await settle();
  };
  return { ...m, lanes, block, pointer };
}

describe('DayGrid', () => {
  it('a row per bookable professional, then who keeps appointments, then Unassigned', async () => {
    const s = await setup([row('a1', 's3', '10:00'), row('a2', null, '11:00')]);
    expect(s.lanes()).toEqual(['s1', 's2', 's3', 'unassigned']);
    expect(s.find('appointment-grid-kept').text()).toBe(
      'Carla Sanz no longer takes new appointments: their appointments for the day stay on their row so you can move them to someone else.',
    );
    expect(s.wrapper.findAll('[data-testid="appointment-grid-hour"]').map((h) => h.text())).toHaveLength(12);
  });

  it('a row that keeps no appointment that day is not shown, and no warning either', async () => {
    const s = await setup([], { lanes: LANES.slice(0, 2) });
    expect(s.lanes()).toEqual(['s1', 's2']);
    expect(s.find('appointment-grid-kept').exists()).toBe(false);
  });

  it('places each appointment by its time and length, and paints the blocks', async () => {
    const s = await setup([row('a1', 's1', '10:30', 45, { customer_name: '' })]);
    const style = s.block('a1').attributes('style');
    expect(style).toContain('left: 240px');
    expect(style).toContain('width: 72px');
    expect(s.block('a1').text()).toContain('Deleted customer');
    expect(s.wrapper.findAll('[data-testid="appointment-grid-block"]')).toHaveLength(3);
  });

  // outfitkit#71 · appointments#77: two appointments of the same professional at once share the row side by
  // side (a track each, as Google Calendar), never one on top of the other; one that follows takes the row back.
  it('appointments at the same time share the row, each in its own track', async () => {
    const s = await setup([row('a1', 's1', '10:00', 60), row('a2', 's1', '10:30', 30), row('a3', 's1', '11:00', 30)]);
    const box = (id: string) => {
      const style = s.block(id).attributes('style') ?? '';
      return { top: Number(/top: ([\d.]+)px/.exec(style)?.[1]), height: Number(/height: ([\d.]+)px/.exec(style)?.[1]) };
    };
    const [first, second, third] = [box('a1'), box('a2'), box('a3')];
    expect(second.top).toBeGreaterThanOrEqual(first.top + first.height);
    expect(third.top).toBe(first.top);
  });

  it('tapping a free slot books there; on a row that takes no bookings, only the time', async () => {
    const s = await setup([row('a1', 's3', '10:00')]);
    await click(s.wrapper.find('[data-testid="appointment-grid-slot"][data-lane="s2"][data-time="16:30"]').element);
    await click(s.wrapper.find('[data-testid="appointment-grid-slot"][data-lane="s3"][data-time="09:00"]').element);
    expect(s.wrapper.emitted('slot')).toEqual([
      [{ staffId: 's2', staffName: 'Bea Ruiz', time: '16:30' }],
      [{ staffId: null, staffName: '', time: '09:00' }],
    ]);
    expect(s.wrapper.find('[data-testid="appointment-grid-slot"][data-lane="s2"][data-time="16:30"]').attributes('aria-label')).toBe(
      'Book with Bea Ruiz at 4:30 PM',
    );
  });

  it('shades the hours the business is closed (Schedules) and books none of them', async () => {
    const hours = (over: Partial<DayHours> = {}): DayHours => ({
      date: '2026-10-19',
      source: 'weekly',
      rule_id: null,
      name: '',
      is_closed: false,
      intervals: [],
      spans: [
        { start: '2026-10-19T09:00:00', end: '2026-10-19T14:00:00' },
        { start: '2026-10-19T16:00:00', end: '2026-10-19T19:00:00' },
      ],
      ...over,
    });
    const closed = (s: Awaited<ReturnType<typeof setup>>) =>
      s.wrapper.findAll('[data-testid="appointment-grid-lane"][data-lane="s1"] [data-testid="appointment-grid-closed"]').map((c) => c.attributes('style'));
    const slot = (s: Awaited<ReturnType<typeof setup>>, time: string) => s.wrapper.find(`[data-testid="appointment-grid-slot"][data-lane="s1"][data-time="${time}"]`);

    const open = await setup([], { hours: hours() });
    // 08:00–09:00, 14:00–16:00 and 19:00–20:00 of the 08:00–20:00 window, at 1.6 px a minute.
    expect(closed(open)).toEqual(['left: 0px; width: 96px;', 'left: 576px; width: 192px;', 'left: 1056px; width: 96px;']);
    expect(['08:30', '09:00', '14:30', '16:00', '19:00'].map((time) => slot(open, time).exists())).toEqual([false, true, false, true, false]);

    const shut = await setup([], { hours: hours({ is_closed: true, spans: [] }) });
    expect(closed(shut)).toEqual(['left: 0px; width: 1152px;']);
    expect(shut.wrapper.findAll('[data-testid="appointment-grid-slot"]')).toHaveLength(0);

    // No rule of hours at all: nothing is shaded (the business never refuses on hours).
    const free = await setup([], { hours: hours({ source: 'none', spans: [] }) });
    expect(closed(free)).toEqual([]);
    expect(slot(free, '08:30').exists()).toBe(true);
  });

  it('tapping an appointment opens it', async () => {
    const item = row('a1', 's1', '10:00');
    const s = await setup([item]);
    await click(s.block('a1').element);
    expect(s.wrapper.emitted('open')).toEqual([[item]]);
  });

  it('dragging an appointment moves it to another time and row', async () => {
    const item = row('a1', 's1', '10:00');
    const s = await setup([item]);
    const el = s.block('a1').element;
    await s.pointer(el, 'pointerdown', 100, 100);
    await s.pointer(el, 'pointermove', 196, 156); // one hour right, one row down
    await s.pointer(el, 'pointerup', 196, 156);
    expect(s.wrapper.emitted('move')).toEqual([[{ row: item, staffId: 's2', time: '11:00' }]]);
    await click(el);
    expect(s.wrapper.emitted('open')).toBeUndefined();
  });

  it('a finger must hold the appointment before dragging it, and nothing moves into the past', async () => {
    const s = await setup([row('a1', 's1', '10:00')]);
    const el = s.block('a1').element;
    await s.pointer(el, 'pointerdown', 100, 100, 'touch');
    await s.pointer(el, 'pointermove', 196, 100, 'touch');
    await s.pointer(el, 'pointerup', 196, 100, 'touch');
    expect(s.wrapper.emitted('move')).toBeUndefined();
    await s.pointer(el, 'pointerdown', 100, 100);
    await s.pointer(el, 'pointermove', -300, 100);
    await s.pointer(el, 'pointerup', -300, 100);
    expect(s.wrapper.emitted('move')).toBeUndefined();
  });

  it('a finished or charged appointment does not move, and without the right nothing is booked', async () => {
    const s = await setup([row('a1', 's1', '10:00', 30, { status: 'completed' })], { canBook: false });
    const el = s.block('a1').element;
    await s.pointer(el, 'pointerdown', 100, 100);
    await s.pointer(el, 'pointermove', 196, 100);
    await s.pointer(el, 'pointerup', 196, 100);
    expect(s.wrapper.emitted('move')).toBeUndefined();
    expect(s.wrapper.findAll('[data-testid="appointment-grid-slot"]')).toHaveLength(0);
  });
});
