// The agenda's bar (WORKBOOK «Agenda»): the day (‹ date › and «Today», and the calendar to jump to a
// date), «Filter by status», «N to confirm» when customers' bookings wait, the «List · By professional ·
// Repeating» switch and, for the first two, «Day · Week» (a week steps seven days). A device on another
// zone is told the agenda shows the business's clock.
import { DateField } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountAppointment, settle } from '../__tests__/mount-appointment';
import AgendaToolbar from './AgendaToolbar.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const here = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const m = await mountAppointment(AgendaToolbar, {
    props: { day: '2026-10-21', view: 'list', span: 'day', status: '', toConfirm: 0, today: '2026-10-14', zone: here, ...props },
    locale,
  });
  const last = (name: string) => m.wrapper.emitted(name)?.at(-1);
  const calendar = () => m.wrapper.getComponent(DateField);
  return { ...m, last, calendar };
}

describe('AgendaToolbar', () => {
  it('steps day by day and comes back to today', async () => {
    const s = await setup();
    expect(s.find('appointment-toolbar-date').text()).toBe('Wednesday, October 21, 2026');
    await click(s.find('appointment-toolbar-next').element);
    expect(s.last('update:day')).toEqual(['2026-10-22']);
    await click(s.find('appointment-toolbar-prev').element);
    expect(s.last('update:day')).toEqual(['2026-10-21']);
    await click(s.find('appointment-toolbar-today').element);
    expect(s.last('update:day')).toEqual(['2026-10-14']);
    s.calendar().vm.$emit('update:modelValue', '2026-12-01');
    await settle();
    expect(s.last('update:day')).toEqual(['2026-12-01']);
  });

  // The app's own calendar, in the app's language and colours, never the device's date picker; the agenda always
  // shows a day, so it has no «Clear».
  it('the day is a date field of the app that jumps to the day picked', async () => {
    const s = await setup();
    expect(s.calendar().props()).toMatchObject({ testid: 'appointment-toolbar-calendar', modelValue: '2026-10-21', label: 'Date', required: true });
    expect((s.find('appointment-toolbar-calendar').element as HTMLElement & { value?: string }).value).toBe('10/21/2026');
    s.calendar().vm.$emit('update:modelValue', '');
    await settle();
    expect(s.last('update:day')).toBeUndefined();
  });

  it('a week steps seven days and says which week', async () => {
    const s = await setup({ span: 'week' });
    expect(s.find('appointment-toolbar-date').text()).toBe('Week of Monday, October 19, 2026');
    await click(s.find('appointment-toolbar-next').element);
    expect(s.last('update:day')).toEqual(['2026-10-28']);
    expect(s.find('appointment-toolbar-next').attributes('aria-label')).toBe('Next week');
  });

  it('switches views and spans, filters by status, and leads to the bookings to confirm', async () => {
    const s = await setup({ toConfirm: 3 });
    await ionValue(s.find('appointment-toolbar-view').element, 'staff');
    expect(s.last('update:view')).toEqual(['staff']);
    await ionValue(s.find('appointment-toolbar-span').element, 'week');
    expect(s.last('update:span')).toEqual(['week']);
    await ionValue(s.find('appointment-toolbar-status').element, 'no_show');
    expect(s.last('update:status')).toEqual(['no_show']);
    expect(s.find('appointment-toolbar-to-confirm').text()).toBe('3 to confirm');
    await click(s.find('appointment-toolbar-to-confirm').element);
    expect(s.last('update:status')).toEqual(['pending']);
  });

  it('the repeating view has no day, and a device on another zone is told', async () => {
    const s = await setup({ view: 'series', zone: 'Pacific/Kiritimati' });
    expect(s.find('appointment-toolbar-date').exists()).toBe(false);
    expect(s.find('appointment-toolbar-span').exists()).toBe(false);
    expect(s.find('appointment-toolbar-zone').text()).toContain('The agenda always shows the business clock: Pacific/Kiritimati.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    await settle();
    expect(s.find('appointment-toolbar-date').text()).toBe('miércoles, 21 de octubre de 2026');
    expect(s.find('appointment-toolbar-today').text()).toBe('Hoy');
    expect(s.calendar().props('label')).toBe('Fecha');
    expect((s.find('appointment-toolbar-calendar').element as HTMLElement & { value?: string }).value).toBe('21/10/2026');
  });
});
