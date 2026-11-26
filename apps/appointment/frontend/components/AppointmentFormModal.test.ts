// APPOINTMENT-F01, F04, F14, F22: the booking panel, wide in two columns (who and what; when) and the whole screen on
// a phone. «New appointment» asks for the Customer (Customers' own search, which also creates a card), one or more
// Services, the Professional (only who does them all), the Day, «Duration (min)» (one tap, the services' sum unless
// changed), the Time (the free times, or another one) and the notes, folded; its foot says what is chosen. «Add
// appointment» books it. An overlap asks first («Book anyway» / «Pick another time»); a refusal goes on top, a bad
// field under it, and what was typed stays. «Edit appointment» sends only what changed, asks «This appointment only»
// / «This and all following» for a series and keeps the history folded below.
import { ConfirmDialog, FormModal } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import { BOOKED, fillNew, READS, SERVICES, setup } from '../__tests__/appointment-form';
import { click, ionValue, page, POLISH, settle } from '../__tests__/mount-appointment';
import AppointmentHistory from './AppointmentHistory.vue';
import FreeSlots from './FreeSlots.vue';

describe('AppointmentFormModal: New appointment', () => {
  it('asks for customer, services, professional, day, length and time, wide in two columns', async () => {
    const s = await setup();
    expect(s.inDoc('appointment-form')?.getAttribute('aria-label')).toBe('New appointment');
    expect(s.wrapper.findComponent(FormModal).props()).toMatchObject({ size: 'xl', phoneLayout: 'fullscreen' });
    const within = (part: string, names: string[]) => names.every((name) => s.inDoc(`appointment-form-${part}`)!.contains(s.inDoc(`appointment-form-${name}`)));
    expect([within('who', ['customer', 'staff']), within('when', ['day', 'duration', 'time']), within('more', ['notes-fold'])]).toEqual([true, true, true]);
    expect([s.field('day').label, s.field('time').label]).toEqual(['Day', 'Time']);
    expect(s.inDoc('appointment-form-other-time')?.textContent).toContain('Enter another time');
    expect(s.staffPicker().props('label')).toBe('Professional');
    expect(s.submit().textContent).toContain('Add appointment');
    expect(s.submit().disabled).toBe(true);
  });

  it('says what is missing in the place of the free times, and asks them once services, professional and day are there', async () => {
    const s = await setup();
    expect(s.inDoc('appointment-form-slots-unset')?.textContent).toContain('Pick the services, a professional and a day to see the free times.');
    expect(s.wrapper.findComponent(FreeSlots).exists()).toBe(false);
    await s.addService('cut', 'Haircut');
    await s.pickStaff('s1', 'Ana López');
    expect(s.inDoc('appointment-form-slots-unset')).toBeNull();
    expect(s.wrapper.findComponent(FreeSlots).props()).toMatchObject({ staffName: 'Ana López', today: '2026-10-14', date: '2026-10-14' });
  });

  it('a day the professional does not work hides «Enter another time»: the server would refuse any time of it', async () => {
    const s = await setup();
    await fillNew(s);
    s.wrapper.findComponent(FreeSlots).vm.$emit('off', true);
    await settle();
    expect(s.inDoc('appointment-form-other-time')).toBeNull();
    s.wrapper.findComponent(FreeSlots).vm.$emit('off', false);
    await settle();
    expect(s.field('time')).not.toBeNull();
  });

  it('the foot says the time chosen, its length, the day and the professional; nothing without a time', async () => {
    const s = await setup();
    expect(s.inDoc('appointment-form-summary')?.textContent?.trim()).toBe('');
    await fillNew(s);
    expect(s.inDoc('appointment-form-chosen-span')?.textContent).toBe('10:00 AM – 11:30 AM · 90 min');
    expect(s.inDoc('appointment-form-chosen-where')?.textContent).toBe('Mon, Oct 19 · Ana López');
    await click(s.inDoc('appointment-form-duration-45'));
    expect(s.inDoc('appointment-form-chosen-span')?.textContent).toBe('10:00 AM – 10:45 AM · 45 min');
  });

  it('books with the services in order, the professional and the wall-clock time; the minutes are their sum', async () => {
    const s = await setup();
    await fillNew(s);
    expect(s.held()).toBe('90');
    expect(s.wrapper.findComponent(FreeSlots).props()).toMatchObject({ date: '2026-10-19', serviceIds: ['cut', 'colour'], staffId: 's1' });
    s.answer(201, BOOKED);
    await click(s.submit());
    const sent = s.sent().filter((call) => call.path === '/api/appointment/appointments');
    expect(sent).toEqual([
      {
        method: 'POST',
        path: '/api/appointment/appointments',
        query: {},
        body: {
          customer_id: 'c1',
          services: [{ service_id: 'cut' }, { service_id: 'colour' }],
          staff_id: 's1',
          start: '2026-10-19T10:00',
          notes: '',
          internal_notes: '',
          confirm_overlap: false,
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    expect(s.wrapper.emitted('saved')?.[0]).toEqual([BOOKED]);
  });

  it('the minutes and the total are the professional’s own for each service (Services · «Who does it»)', async () => {
    const s = await setup();
    const eligible = (memberId: string, fullName: string, duration: number, price: number, own: boolean) => ({
      member_id: memberId,
      full_name: fullName,
      color: '',
      booking_buffer: 0,
      custom_duration: own ? duration : null,
      custom_price: own ? price : null,
      is_primary: own,
      duration,
      price,
    });
    s.net.onApi(({ url }) => {
      const asked = new URL(url, 'http://a.localhost');
      if (asked.pathname === '/api/service/services/for_sale') return Response.json(SERVICES);
      if (asked.pathname === '/api/staff/members') return Response.json(page([{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }]));
      if (asked.pathname === '/api/service/assignments/eligible' && asked.searchParams.get('service_id') === 'cut') {
        return Response.json(page([eligible('s1', 'Ana López', 45, 2500, true), eligible('s2', 'Bea Ruiz', 30, 2000, false)]));
      }
      return Response.json(page([]));
    });
    await s.businessIn();
    await fillNew(s);
    // Ana does a haircut in 45 minutes for €25.00; the colour, nobody's own: the catalog's.
    expect(s.held()).toBe('105');
    expect(s.inDoc('appointment-form-total')?.textContent).toContain('€70.00');
    await s.pickStaff('s2', 'Bea Ruiz');
    expect(s.held()).toBe('90');
    expect(s.inDoc('appointment-form-total')?.textContent).toContain('€65.00');
    // Minutes typed by hand stay.
    await s.typeMinutes('50');
    await s.pickStaff('s1', 'Ana López');
    expect(s.held()).toBe('50');
  });

  it('the total of four figures groups its thousands, in both languages (hub#632)', async () => {
    const dear = page([
      { id: 'cut', name: 'Haircut', price: 100000, duration_minutes: 30, is_bookable: true },
      { id: 'colour', name: 'Colour', price: 23456, duration_minutes: 60, is_bookable: true },
    ]);
    for (const [locale, total] of [['es', '1.234,56\u00a0€'], ['en', '€1,234.56']] as const) {
      const s = await setup({}, locale);
      s.answerBy({ ...READS, '/api/service/services/for_sale': [200, dear] });
      await s.businessIn();
      await s.addService('cut', 'Haircut');
      await s.addService('colour', 'Colour');
      expect(s.inDoc('appointment-form-total')?.textContent).toContain(total);
      s.wrapper.unmount();
    }
  });

  it('the total is in the business’s currency: złoty in a business in Poland, a dash until it answers (hub#577, hub#947)', async () => {
    const s = await setup({}, 'es');
    await s.addService('cut', 'Haircut');
    await s.addService('colour', 'Colour');
    expect(s.inDoc('appointment-form-total')?.textContent).toMatch(/: —$/);
    await s.businessIn(POLISH);
    expect(s.inDoc('appointment-form-total')?.textContent).toMatch(/: 65,00\u00a0zł$/);
    expect(s.inDoc('appointment-form-total')?.textContent).not.toContain('€');
  });

  it('sends the minutes only when typed, and a free time fills the time', async () => {
    const s = await setup();
    await fillNew(s);
    await s.typeMinutes('75');
    s.wrapper.findComponent(FreeSlots).vm.$emit('pick', '11:15');
    await settle();
    expect(s.kept('time')).toBe('11:15');
    s.answer(201, BOOKED);
    await click(s.submit());
    const body = s.sent().find((call) => call.path === '/api/appointment/appointments')?.body as Record<string, unknown>;
    expect([body.start, body.duration_minutes]).toEqual(['2026-10-19T11:15', 75]);
  });

  it('a tap on a length sends it, and «Use the sum» goes back to following the services', async () => {
    const s = await setup();
    await fillNew(s);
    await click(s.inDoc('appointment-form-duration-60'));
    expect(s.wrapper.findComponent(FreeSlots).props('durationMinutes')).toBe(60);
    await click(s.inDoc('appointment-form-duration-use-sum'));
    expect([s.held(), s.wrapper.findComponent(FreeSlots).props('durationMinutes')]).toEqual(['90', null]);
    await s.addService('cut', 'Haircut');
    s.answer(201, BOOKED);
    await click(s.submit());
    const body = s.sent().find((call) => call.path === '/api/appointment/appointments')?.body as Record<string, unknown>;
    expect(body.duration_minutes).toBeUndefined();
  });

  it('the notes come folded; a refusal of one opens it', async () => {
    const s = await setup();
    expect([s.field('notes'), s.field('internal_notes')]).toEqual([null, null]);
    await fillNew(s);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { internal_notes: 'Too long.' } } });
    await click(s.submit());
    expect(s.field('internal_notes').errorText).toBe('Too long.');
  });

  it('asks before booking on top of another appointment, and «Book anyway» books', async () => {
    const s = await setup();
    await fillNew(s);
    const message = 'This time overlaps with APT-1 Pepa (10:00–10:30). Book it anyway?';
    s.answer(409, { error: { code: 'appointment.overlap_needs_confirmation', message } });
    await click(s.submit());
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === 'appointment-overlap')!;
    expect([dialog.props('open'), dialog.props('title'), dialog.props('message')]).toEqual([true, 'Overlapping appointment', message]);
    expect([dialog.props('confirmLabel'), dialog.props('cancelLabel')]).toEqual(['Book anyway', 'Pick another time']);
    s.answer(201, BOOKED);
    dialog.vm.$emit('confirm');
    await settle();
    const bodies = s.sent().filter((call) => call.path === '/api/appointment/appointments').map((call) => (call.body as Record<string, unknown>).confirm_overlap);
    expect(bodies).toEqual([false, true]);
  });

  it('a refusal goes on top and a bad field under it, and what was typed stays', async () => {
    const s = await setup();
    await fillNew(s);
    s.answer(409, { error: { code: 'appointment.outside_schedule', message: 'That time is outside the business’s opening hours.' } });
    await click(s.submit());
    expect(s.inDoc('appointment-form-error')?.textContent).toContain('outside the business’s opening hours');
    s.answer(422, { error: { code: 'appointment.invalid_local_time', message: 'x', fields: { start: 'That time does not exist.' } } });
    await click(s.submit());
    expect(s.field('time').errorText).toBe('That time does not exist.');
    expect(s.kept('time')).toBe('10:00');
  });

  // The customer is chosen in Customers' own search, in a window of its own: no field of the form is typed in, and its
  // refusal is a line under the chooser. Choosing another customer takes that line away at once, and only it (hub#1448).
  it('a refused customer’s line goes when another customer is chosen, before booking again; another field’s stays', async () => {
    const s = await setup();
    await fillNew(s);
    const gone = 'That customer is no longer in the business.';
    const time = 'That time does not exist.';
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { customer_id: gone, start: time } } });
    await click(s.submit());
    const said = () => s.field('customer').textContent ?? '';
    expect(said()).toContain(gone);
    s.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', {
      customer_id: 'c2',
      customer_name: 'Marta Gil',
      customer_tax_id: '',
      customer_address: '',
      customer_country: '',
    });
    await settle();
    expect(said()).not.toContain(gone);
    expect(s.field('time').errorText).toBe(time);
    expect(s.sent().filter((call) => call.path === '/api/appointment/appointments')).toHaveLength(1);
  });

  // The day and the time are the app's own pickers (never the device's), shown as read; a picked time counts at once.
  it('the day and the time are the app’s pickers, shown as read, and a picked time counts at once', async () => {
    const s = await setup();
    expect([s.field('day').readonly, s.field('time').readonly]).toEqual([true, true]);
    await s.pickCustomer();
    await s.addService('cut', 'Haircut');
    await s.pickStaff('s1', 'Ana López');
    await s.pick('day', '2026-10-19');
    expect(s.submit().disabled).toBe(true);
    await s.pick('time', '10:00');
    expect([s.field('day').value, s.field('time').value, s.submit().disabled]).toEqual(['10/19/2026', expect.stringMatching(/^10:00\sAM$/), false]);
  });

  // Services or professionals that cannot load are never an empty list nor only the
  // appointment's own: their search fails, and the picker says so with «Retry» (Combo's error state).
  it('services and professionals that cannot load fail their search, new and edited alike', async () => {
    const broken: Record<string, [number, unknown]> = {
      '/api/service/services/for_sale': [500, { error: { code: 'internal_error', message: 'Internal error' } }],
      '/api/staff/members': [500, { error: { code: 'internal_error', message: 'Internal error' } }],
      '/api/service/assignments/eligible': [500, { error: { code: 'internal_error', message: 'Internal error' } }],
    };
    for (const appointment of [null, BOOKED]) {
      const s = await setup({ appointment });
      s.answerBy(broken);
      const search = (picker: ReturnType<typeof s.staffPicker>) => (picker.props('search') as (q: string) => Promise<unknown>)('');
      await expect(search(s.servicePicker())).rejects.toBeTruthy();
      await expect(search(s.staffPicker())).rejects.toBeTruthy();
    }
  });

  it('warns that the time is in the past', async () => {
    const s = await setup();
    await fillNew(s);
    expect(s.inDoc('appointment-form-past')).toBeNull();
    await s.pick('day', '2026-10-13');
    expect(s.inDoc('appointment-form-past')?.textContent).toContain('starts in the past');
  });

  it('comes with the professional and the time of the tapped slot', async () => {
    const s = await setup({ preset: { day: '2026-10-19', time: '16:30', staffId: 's2', staffName: 'Bea Ruiz' } });
    expect(s.staffPicker().props('modelValue')).toEqual({ id: 's2', label: 'Bea Ruiz' });
    expect([s.kept('day'), s.kept('time')]).toEqual(['2026-10-19', '16:30']);
  });

  it('an employee books for herself only', async () => {
    const s = await setup({ ownStaff: { id: 's2', name: 'Bea Ruiz' } });
    expect(s.staffPicker().props('modelValue')).toEqual({ id: 's2', label: 'Bea Ruiz' });
    expect(s.staffPicker().props('disabled')).toBe(true);
    expect(s.inDoc('appointment-form-own')?.textContent).toBe('You book your own appointments.');
  });

  it('a professional who does not do the services is taken away with a warning', async () => {
    const s = await setup();
    await s.pickStaff('s1', 'Ana López');
    s.answerBy({
      '/api/service/services/for_sale': [200, SERVICES],
      '/api/staff/members': [200, page([{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }])],
      '/api/service/assignments/eligible': [200, page([{ member_id: 's2', full_name: 'Bea Ruiz' }])],
    });
    await s.addService('colour', 'Colour');
    await settle();
    expect(s.staffPicker().props('modelValue')).toBeNull();
    expect(s.inDoc('appointment-form-staff-warning')?.textContent).toContain('does not perform these services');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.inDoc('appointment-form')?.getAttribute('aria-label')).toBe('Nueva cita');
    expect([s.field('day').label, s.field('time').label]).toEqual(['Día', 'Hora']);
    expect(s.inDoc('appointment-form-other-time')?.textContent).toContain('Introducir otra hora');
    expect(s.inDoc('appointment-form-slots-unset')?.textContent).toContain('Elige los servicios, un profesional y un día para ver las horas libres.');
    expect(s.submit().textContent).toContain('Añadir cita');
  });
});

describe('AppointmentFormModal: Edit appointment', () => {
  it('comes filled in, sends only what changed and keeps the history folded below', async () => {
    const s = await setup({ appointment: BOOKED });
    expect(s.inDoc('appointment-form')?.getAttribute('aria-label')).toBe('Edit appointment');
    expect(s.inDoc('appointment-form-booked')?.textContent).toMatch(/Lucía Pérez.*APT-20261019-0001.*Confirmed/s);
    expect(s.inDoc('appointment-form-customer')).toBeNull();
    expect([s.kept('day'), s.kept('time'), s.held()]).toEqual(['2026-10-19', '10:00', '30']);
    expect(s.wrapper.findComponent(AppointmentHistory).exists()).toBe(false);
    await s.unfold('history');
    expect(s.wrapper.findComponent(AppointmentHistory).props('appointmentId')).toBe('a1');
    expect(s.wrapper.findComponent(FreeSlots).props('excludeId')).toBe('a1');
    await s.pick('time', '11:00');
    await s.unfold('notes');
    await ionValue(s.field('notes'), 'Bring photo', 'ionInput');
    s.answer(200, { ...BOOKED, start: '2026-10-19T11:00:00+02:00' });
    await click(s.submit());
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      {
        method: 'POST',
        path: '/api/appointment/appointments/update',
        query: {},
        body: { id: 'a1', start: '2026-10-19T11:00', notes: 'Bring photo', confirm_overlap: false },
      },
    ]);
  });

  it('notes with text come open; «Use the sum» sends the sum when the length had been changed', async () => {
    const s = await setup({ appointment: { ...BOOKED, internal_notes: 'Warm water', duration_minutes: 50 } });
    expect(s.field('internal_notes').value).toBe('Warm water');
    expect(s.field('notes')).toBeNull();
    expect(s.held()).toBe('50');
    await click(s.inDoc('appointment-form-duration-60'));
    await click(s.inDoc('appointment-form-duration-use-sum'));
    expect(s.held()).toBe('30');
    s.answer(200, BOOKED);
    await click(s.submit());
    const body = s.sent().find((call) => call.path === '/api/appointment/appointments/update')?.body as Record<string, unknown>;
    expect(body.duration_minutes).toBe(30);
  });

  it('a charged appointment keeps its services and professional: both pickers are locked', async () => {
    const s = await setup({ appointment: { ...BOOKED, sale_id: 'sale1' } });
    expect([s.servicePicker().props('disabled'), s.staffPicker().props('disabled')]).toEqual([true, true]);
    const open = await setup({ appointment: BOOKED });
    expect([open.servicePicker().props('disabled'), open.staffPicker().props('disabled')]).toEqual([false, false]);
  });

  it('a series occurrence asks the scope; «This and all following» edits the series from its date', async () => {
    const s = await setup({ appointment: { ...BOOKED, recurring_id: 'r1', occurrence_date: '2026-10-19' } });
    await s.pick('time', '12:00');
    await click(s.submit());
    const scope = s.inDoc('appointment-scope');
    expect(scope?.textContent).toContain('This appointment is part of a repeating series.');
    s.answer(200, { recurring: {}, moved: 3, cancelled: 0, locked: 1, skipped: [], booked: 0 });
    await click(s.inDoc('appointment-scope-following'));
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      {
        method: 'POST',
        path: '/api/appointment/recurring/update',
        query: {},
        body: { id: 'r1', from_date: '2026-10-19', time: '12:00' },
      },
    ]);
    // Only what happened, never «0 cancelled».
    expect(s.wrapper.emitted('outcome')?.[0]).toEqual(['3 appointments moved · 1 left alone because it is already charged']);
  });
});

describe('AppointmentFormModal: fields refused with the same words (hub#888)', () => {
  // A new appointment's fields, each refused under its own key; the time says the refusal of `start`, and the search
  // that adds a service (ServicesField's Combo) the refusal of `services`.
  const FIELD_OF: Record<string, string> = { start: 'time', services: 'service-add' };
  itTellsTheCorrectedFieldApart(['services', 'staff', 'start', 'minutes', 'notes', 'internal_notes'], async (locale, refusal) => {
    const s = await setup({}, locale);
    await fillNew(s);
    s.answer(422, refusal);
    return { field: (key) => s.field(FIELD_OF[key] ?? key), send: () => click(s.submit()), settle };
  }, 'start');
});

describe('AppointmentFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('appointment-form'),
      change: () => s.pick('time', '10:00'),
      restore: () => s.pick('time', ''),
    });
  });
});
