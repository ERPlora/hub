// SCHEDULE-F05 «Añadir un cambio temporal» and F13 «Corregir»: «New override» — From, To, Reason, Status
// (closed to begin with) and the interval editor when open — and «Add override»; a row opens «Edit ·
// {reason}» with «Save». It waits for both dates and a reason. A range over another override (409) is
// said under From, an end before the start (422) under To.
import { describe, expect, it, vi } from 'vitest';

import type { OverrideOut } from '../operations';
import { click, ionValue, mountSchedule, settle } from '../__tests__/mount-schedule';
import OverrideFormModal from './OverrideFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; disabled?: boolean; errorText?: string; type?: string };

const SUMMER: OverrideOut = {
  id: 'o1',
  start_date: '2026-07-01',
  end_date: '2026-08-31',
  reason: 'Summer hours',
  is_closed: false,
  intervals: [{ open_time: '08:00:00', close_time: '15:00:00' }],
};

async function setup(override: OverrideOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountSchedule(OverrideFormModal, { props: { open: true, override }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const field = (name: string) => m.inDoc(`schedule-override-form-${name}`) as Control;
  const submit = () => m.inDoc('schedule-override-form-submit') as Control;
  async function fill(values: Record<string, string>) {
    for (const [name, value] of Object.entries(values)) await ionValue(field(name), value, 'ionInput');
  }
  return { ...m, field, submit, fill };
}

describe('OverrideFormModal (SCHEDULE-F05, F13)', () => {
  it('«New override»: From, To, Reason, Status closed and «Add override»', async () => {
    const s = await setup();
    expect(s.inDoc('schedule-override-form')?.getAttribute('aria-label')).toBe('New override');
    expect(['start_date', 'end_date', 'reason', 'status'].map((n) => s.field(n).label)).toEqual(['From', 'To', 'Reason', 'Status']);
    expect([s.field('start_date').type, s.field('end_date').type, s.field('status').value]).toEqual(['date', 'date', 'closed']);
    expect(s.submit().textContent?.trim()).toBe('Add override');
  });

  it('waits for both dates and a reason, then sends schedule.override.create and closes', async () => {
    const s = await setup();
    s.answer(201, { ...SUMMER, id: 'o9' });
    await s.fill({ start_date: '2026-08-01', end_date: '2026-08-15' });
    expect(s.submit().disabled).toBe(true);
    await s.fill({ reason: ' Holidays ' });
    expect(s.submit().disabled).toBe(false);
    await click(s.submit());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/schedule/overrides',
        query: {},
        body: { start_date: '2026-08-01', end_date: '2026-08-15', reason: 'Holidays', is_closed: true, intervals: [] },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('an override over another (409) is said under From, an end before the start (422) under To', async () => {
    const s = await setup();
    const clash = 'Those dates overlap the temporary change “Holidays” (08/01/2026 – 08/31/2026).';
    s.answer(409, { error: { code: 'schedule.override_overlaps', message: clash, fields: { start_date: clash } } });
    await s.fill({ start_date: '2026-08-20', end_date: '2026-09-05', reason: 'More' });
    await click(s.submit());
    expect(s.field('start_date').errorText).toBe(clash);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { end_date: 'The end date cannot be before the start date.' } } });
    await click(s.submit());
    expect(s.field('end_date').errorText).toBe('The end date cannot be before the start date.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('a row opens «Edit · {reason}» with its hours, and «Save» sends schedule.override.update', async () => {
    const s = await setup(SUMMER);
    expect(s.inDoc('schedule-override-form')?.getAttribute('aria-label')).toBe('Edit · Summer hours');
    expect([s.field('start_date').value, s.field('end_date').value, s.field('reason').value, s.field('status').value]).toEqual([
      '2026-07-01',
      '2026-08-31',
      'Summer hours',
      'open',
    ]);
    s.answer(200, SUMMER);
    await s.fill({ end_date: '2026-09-15' });
    await click(s.submit());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/schedule/overrides/update',
        query: {},
        body: {
          id: 'o1',
          start_date: '2026-07-01',
          end_date: '2026-09-15',
          reason: 'Summer hours',
          is_closed: false,
          intervals: [{ open_time: '08:00', close_time: '15:00' }],
        },
      },
    ]);
  });

  it('speaks Spanish with the old words', async () => {
    const s = await setup(null, 'es');
    expect(s.inDoc('schedule-override-form')?.getAttribute('aria-label')).toBe('Nuevo cambio temporal');
    expect([s.field('start_date').label, s.field('end_date').label, s.field('reason').label, s.submit().textContent?.trim()]).toEqual([
      'Desde',
      'Hasta',
      'Motivo',
      'Añadir cambio temporal',
    ]);
  });
});
