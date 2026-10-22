// The filters of a VeriFactu list (Records: status, type, invoice type, environment, dates and total; Events: type,
// severity and dates): the funnel button with the count in use, opening a panel with the closed lists already
// translated, the days and the amounts (euros). A change applies at once; «Clear filters» drops them all; «Done»
// closes. An amount that is not one is marked under its field and never reaches the server.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountVerifactu } from '../__tests__/mount-verifactu';
import ListFilters from './ListFilters.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const prop = (el: Element, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

async function setup(modelValue: Record<string, string> = {}, list: 'records' | 'events' = 'records', locale: 'en' | 'es' = 'en') {
  const m = await mountVerifactu(ListFilters, { props: { modelValue, list }, locale });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
  const openIt = () => click(m.find('verifactu-filters').element);
  const field = (key: string) => m.find(`verifactu-filter-${key}`);
  return { ...m, emitted, openIt, field };
}

describe('ListFilters', () => {
  it('is the funnel button with the count of filters in use (a range counts once)', async () => {
    expect((await setup()).find('verifactu-filters').text()).toBe('Filters');
    const some = await setup({ status: 'rejected', issue_date_from: '2026-10-01', issue_date_to: '2026-10-14' });
    expect(some.find('verifactu-filters-count').text()).toBe('2');
  });

  it('records: status, type, invoice type, environment, days and totals', async () => {
    const s = await setup();
    await s.openIt();
    expect(s.field('status').findAll('ion-select-option').map((o) => o.text())).toEqual([
      'Any',
      'Pending',
      'Sent, no answer',
      'Accepted',
      'Accepted with errors',
      'Rejected',
    ]);
    expect(s.field('record_type').findAll('ion-select-option').map((o) => o.text())).toEqual(['Any', 'Registration', 'Cancellation']);
    expect(s.field('environment').findAll('ion-select-option').map((o) => o.text())).toEqual(['Any', 'Testing (AEAT test)', 'Production']);
    expect(s.field('invoice_type').findAll('ion-select-option')).toHaveLength(9);
    expect(['issue_date_from', 'total_amount_to'].map((key) => prop(s.field(key).element, 'label'))).toEqual(['Issued from', 'Total up to (€)']);
    expect([prop(s.field('status').element, 'fill'), s.field('status').attributes('mode') ?? prop(s.field('status').element, 'mode')]).toEqual(['outline', 'md']);
  });

  it('events: type, severity and days, in Spanish', async () => {
    const s = await setup({}, 'events', 'es');
    await s.openIt();
    expect(s.field('severity').findAll('ion-select-option').map((o) => o.text())).toEqual(['Cualquiera', 'Depuración', 'Información', 'Aviso', 'Error', 'Crítico']);
    expect(s.field('kind').findAll('ion-select-option').map((o) => o.text())[1]).toBe('Registro creado');
    expect(prop(s.field('date_from').element, 'label')).toBe('Desde');
    expect(s.field('status').exists()).toBe(false);
  });

  it('a change applies at once; blank or «Any» drops it; «Clear filters» drops them all', async () => {
    const s = await setup({ status: 'rejected' });
    await s.openIt();
    await ionValue(s.field('total_amount_from').element, '12,50', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ status: 'rejected', total_amount_from: '12,50' });
    await s.wrapper.setProps({ modelValue: s.emitted().at(-1) });
    await ionValue(s.field('status').element, '');
    expect(s.emitted().at(-1)).toEqual({ total_amount_from: '12,50' });
    await click(s.find('verifactu-filters-clear').element);
    expect(s.emitted().at(-1)).toEqual({});
  });

  it('marks an amount that is not one', async () => {
    const s = await setup({ total_amount_from: '12x' });
    await s.openIt();
    expect(prop(s.field('total_amount_from').element, 'errorText')).toBe('Write an amount in euros, such as 12,50.');
  });
});

