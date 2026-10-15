// The day bar of the book (WORKBOOK «Pantallas · Reservas»): previous day · date · next day, «Today» when
// the book is on another day, the day in words, and three figures — covers, bookings and the next slot
// with what is left, «Full», «No more service today», «No service this day» or «Closed this day».
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountReservation } from '../__tests__/mount-reservation';
import { dayOut, slotLoad } from '../__tests__/rows';
import DayBar from './DayBar.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountReservation(DayBar, {
    props: { day: '2026-10-15', today: '2026-10-15', now: '14:00', figures: dayOut(), failed: null, ...props },
    locale,
  });
  // A figure is a number and its words, each its own element: read them one after the other.
  const text = (id: string) => {
    const el = m.find(`reservation-day-${id}`).element;
    const parts = el.children.length ? [...el.children].map((child) => child.textContent ?? '') : [el.textContent ?? ''];
    return parts.map((part) => part.trim()).filter(Boolean).join(' ');
  };
  return { ...m, text };
}

describe('DayBar', () => {
  it('names the day and gives its covers, bookings and the slot to watch', async () => {
    const s = await setup();
    expect(s.text('name')).toBe('Thursday, October 15');
    expect(s.text('covers')).toBe('11 covers');
    expect(s.text('bookings')).toBe('4 bookings');
    expect(s.text('next-slot')).toBe('1:00 PM–4:00 PM 9 left next slot');
    expect(s.find('reservation-day-today').exists()).toBe(false);
  });

  it('says when the next slot is full, when the service is over, when there is none and when it is closed', async () => {
    const full = await setup({ now: '17:00', figures: dayOut({ slots: [slotLoad({ available: 0, full: true })] }) });
    expect(full.find('reservation-day-next-slot').attributes('data-state')).toBe('full');
    expect(full.text('next-slot')).toContain('Full');
    expect((await setup({ now: '23:50' })).text('next-slot')).toContain('No more service today');
    expect((await setup({ figures: dayOut({ slots: [] }) })).text('next-slot')).toContain('No service this day');
    expect((await setup({ figures: dayOut({ closed: true }) })).text('next-slot')).toContain('Closed this day');
  });

  it('steps the day, takes a typed date and comes back to today', async () => {
    const s = await setup({ day: '2026-10-16' });
    await click(s.find('reservation-day-prev').element);
    await click(s.find('reservation-day-next').element);
    await click(s.find('reservation-day-today').element);
    await ionValue(s.find('reservation-day-input').element, '2026-12-24');
    await ionValue(s.find('reservation-day-input').element, '');
    expect(s.wrapper.emitted('update:day')).toEqual([['2026-10-15'], ['2026-10-17'], ['2026-10-15'], ['2026-12-24']]);
  });

  it('greys the figures while they load and says why when they fail', async () => {
    expect((await setup({ figures: undefined })).find('reservation-day-loading').exists()).toBe(true);
    const failed = await setup({ figures: undefined, failed: 'boom' });
    expect(failed.text('error')).toBe('Could not load the figures of the day');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ day: '2026-10-16' }, 'es');
    expect(s.text('name')).toBe('Viernes, 16 de octubre');
    expect(s.text('covers')).toBe('11 cubiertos');
    expect(s.text('next-slot')).toBe('13:00–16:00 9 libres próxima franja');
    expect(s.text('today')).toBe('Hoy');
  });
});
