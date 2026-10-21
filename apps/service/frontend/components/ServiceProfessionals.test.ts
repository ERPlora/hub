// SERVICE-F31, F32 «Profesionales que lo hacen», inside «Editing service»: the live list of who performs
// the service (`service.assignment.list`), each with what it lasts and costs with them, their main
// service marked; whoever may edit services assigns someone of Staff (searched), with their own minutes
// and price, changes those, marks the main service, switches one off or removes it. Nobody assigned
// says the whole bookable team may do it. Refusals are said above the list; while the list has not
// arrived it says it is loading, and a list that cannot be read says so with «Retry».
import { Combo, InlineFeedback } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import type { AssignmentOut } from '../operations';
import { click, errorFrame, flush, ionChecked, ionValue, mountService, page } from '../__tests__/mount-service';
import ServiceProfessionals from './ServiceProfessionals.vue';

const OP = 'service.assignment.list';
const row = (id: string, over: Partial<AssignmentOut> = {}): AssignmentOut => ({
  id,
  service_id: 's1',
  service_name: 'Cut',
  member_id: `m-${id}`,
  member_name: 'Ana López',
  custom_duration: null,
  custom_price: null,
  is_primary: false,
  is_active: true,
  duration: 30,
  price: 2000,
  ...over,
});
const ROWS = [row('a1', { is_primary: true }), row('a2', { member_name: 'Bea Ruiz', custom_duration: 40, custom_price: 2500, duration: 40, price: 2500 })];

type Control = HTMLElement & { value?: unknown; checked?: boolean; disabled?: boolean; label?: string };

async function setup(options: { canChange?: boolean; locale?: 'en' | 'es' } = {}) {
  const m = await mountService(ServiceProfessionals, {
    props: { serviceId: 's1', canChange: options.canChange ?? true },
    locale: options.locale,
  });
  await m.live();
  const el = (testid: string) => m.inDoc(testid) as Control;
  const member = () => m.wrapper.findComponent(Combo);
  return { ...m, el, member, show: (data: unknown) => m.result(OP, data) };
}

describe('ServiceProfessionals', () => {
  it('follows who performs the service, main service first, with their time and price', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ service_id: 's1', limit: 100 }]);
    await s.show(page(ROWS));
    expect(s.el('service-professionals-row-a1')?.textContent).toContain('Ana López');
    expect(s.el('service-professionals-row-a1')?.textContent).toContain('30 min · €20.00');
    expect(s.el('service-professionals-primary-a1')?.textContent).toContain('Main service');
    expect(s.el('service-professionals-row-a2')?.textContent).toContain('40 min · €25.00');
    expect([s.el('service-professionals-minutes-a2').value, s.el('service-professionals-price-a2').value]).toEqual(['40', '25.00']);
  });

  it('says it is loading until the list arrives, and never «nobody assigned» meanwhile', async () => {
    const s = await setup();
    expect(s.el('service-professionals-loading')?.textContent).toContain('Loading…');
    expect(s.el('service-professionals-empty')).toBeNull();
    await s.show(page(ROWS));
    expect(s.el('service-professionals-loading')).toBeNull();
    expect(s.el('service-professionals-row-a1')).not.toBeNull();
  });

  it('a list that cannot be read says so with the reason and «Retry», which reads it again', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    const failed = s.el('service-professionals-load-error');
    expect(failed?.textContent).toContain('The professionals could not be loaded.');
    expect(failed?.textContent).toContain('msg internal_error');
    expect([s.el('service-professionals-loading'), s.el('service-professionals-empty')]).toEqual([null, null]);
    const streams = s.net.streams.length;
    await click(s.el('service-professionals-retry'));
    await s.reopen();
    expect(s.net.streams.length).toBeGreaterThan(streams);
    await s.show(page(ROWS));
    expect(s.el('service-professionals-load-error')).toBeNull();
    expect(s.el('service-professionals-row-a1')?.textContent).toContain('Ana López');
  });

  it('says the whole bookable team may perform it while nobody is assigned', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.el('service-professionals-empty')?.textContent).toContain('Nobody assigned yet: the whole bookable team may perform it.');
  });

  it('assigns someone of Staff with their own minutes and price, and clears the row', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.el('service-professionals-assign').disabled).toBe(true);
    s.answer(200, row('a3'));
    s.member().vm.$emit('update:modelValue', { id: 'm9', label: 'Cris Gil' });
    await ionValue(s.el('service-professionals-minutes'), '45', 'ionInput');
    await ionValue(s.el('service-professionals-price'), '30', 'ionInput');
    await click(s.el('service-professionals-assign'));
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/service/assignments/assign',
        query: {},
        body: { service_id: 's1', member_id: 'm9', custom_duration: 45, custom_price: 3000 },
      },
    ]);
    expect(s.member().props('modelValue')).toBeNull();
  });

  it('offers only the people of Staff who do not perform it yet', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answerBy({
      '/api/staff/members': [
        200,
        page([
          { id: 'm-a1', full_name: 'Ana López', role_name: null },
          { id: 'm9', full_name: 'Cris Gil', role_name: 'Stylist' },
        ]),
      ],
    });
    const options = await (s.member().props('search') as (q: string) => Promise<unknown[]>)('');
    expect(options).toEqual([{ id: 'm9', label: 'Cris Gil', hint: 'Stylist' }]);
  });

  it('marks the main service, switches one off and removes one', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(200, ROWS[1]);
    await click(s.el('service-professionals-make-primary-a2'));
    await ionChecked(s.el('service-professionals-active-a2'), false);
    await click(s.el('service-professionals-remove-a1'));
    expect(s.sent().map((call) => [call.path, call.body])).toEqual([
      ['/api/service/assignments/update', { id: 'a2', is_primary: true }],
      ['/api/service/assignments/update', { id: 'a2', is_active: false }],
      ['/api/service/assignments/remove', { id: 'a1' }],
    ]);
  });

  it('changes someone’s own minutes and price; empty brings back the service’s', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.el('service-professionals-save-a2').disabled).toBe(true);
    s.answer(200, ROWS[1]);
    await ionValue(s.el('service-professionals-minutes-a2'), '', 'ionInput');
    await ionValue(s.el('service-professionals-price-a2'), '27,50', 'ionInput');
    await click(s.el('service-professionals-save-a2'));
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/service/assignments/update', query: {}, body: { id: 'a2', custom_duration: null, custom_price: 2750 } },
    ]);
  });

  it('says a refusal above the list', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.answer(404, { error: { code: 'service.assignment_not_found', message: 'That assignment does not exist in this business.' } });
    await click(s.el('service-professionals-remove-a1'));
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'service-professionals-error');
    expect([banner?.props('heading'), banner?.text()]).toEqual([
      'The professionals could not be updated',
      expect.stringContaining('That assignment does not exist in this business.'),
    ]);
  });

  it('whoever may not edit services only reads', async () => {
    const s = await setup({ canChange: false });
    await s.show(page(ROWS));
    expect(s.el('service-professionals-row-a1')?.textContent).toContain('Ana López');
    expect(s.el('service-professionals-assign')).toBeNull();
    expect(s.el('service-professionals-remove-a1')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.el('service-professionals')?.textContent).toContain('Profesionales que lo hacen');
    expect(s.el('service-professionals-primary-a1')?.textContent).toContain('Servicio principal');
    expect(s.member().props('label')).toBe('Añadir profesional…');
  });

  it('says loading and the failed read in Spanish too', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.el('service-professionals-loading')?.textContent).toContain('Cargando…');
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.el('service-professionals-load-error')?.textContent).toContain('No se han podido cargar los profesionales.');
    expect(s.el('service-professionals-retry')?.textContent).toContain('Reintentar');
  });
});
