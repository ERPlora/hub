// The filters of the Sales list (SALE-F28: «filter by status, payment, date or total»): the funnel button
// with the count of filters in use, opening a panel with Status (Any · Completed · Voided · Refunded),
// Payment (the server-searched picker), Date from–to and Total from–to (euros). A change applies at once
// (the page asks the server again); «Clear» drops them all; «Done» closes. An amount that is not one is
// marked under its field; what the server refused (a 422 of the list) too.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountSale } from '../../__tests__/mount-sale';
import PaymentMethodPicker from './PaymentMethodPicker.vue';
import SalesFilters from './SalesFilters.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const prop = (el: Element, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

async function setup(modelValue: Record<string, string> = {}, extra: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(SalesFilters, { props: { modelValue, ...extra }, locale });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
  async function openIt() {
    await click(m.find('sales-filters').element);
  }
  const field = (key: string) => m.find(`sales-filter-${key}`);
  return { ...m, emitted, openIt, field };
}

describe('SalesFilters', () => {
  it('is the funnel button «Filters», with the count of filters in use (a range counts once)', async () => {
    const none = await setup();
    expect(none.find('sales-filters').text()).toBe('Filters');
    expect(none.find('sales-filters-count').exists()).toBe(false);
    const some = await setup({ status: 'voided', date_from: '2026-10-01', date_to: '2026-10-14' });
    expect(some.find('sales-filters-count').text()).toBe('2');
    expect(some.find('sales-filters').attributes('aria-label')).toBe('Filters: 2 in use');
  });

  it('opens «Filter sales» with Status, Payment, Date from–to and Total from–to', async () => {
    const s = await setup();
    await s.openIt();
    expect(s.find('sales-filters-panel').attributes('aria-label')).toBe('Filter sales');
    expect(s.field('status').findAll('ion-select-option').map((o) => o.text())).toEqual(['Any', 'Completed', 'Voided', 'Refunded']);
    expect(s.wrapper.findComponent(PaymentMethodPicker).props()).toMatchObject({ valueKey: 'name', label: 'Payment', anyLabel: 'Any' });
    expect(['date_from', 'date_to', 'total_min', 'total_max'].map((key) => prop(s.field(key).element, 'label'))).toEqual([
      'Date from',
      'Date to',
      'Total from',
      'Total to',
    ]);
    expect([prop(s.field('date_from').element, 'type'), prop(s.field('total_min').element, 'inputmode')]).toEqual(['date', 'decimal']);
    for (const key of ['status', 'date_from', 'total_max']) expect([prop(s.field(key).element, 'fill'), s.field(key).attributes('mode') ?? prop(s.field(key).element, 'mode')]).toEqual(['outline', 'md']);
  });

  it('a change applies at once, as a new value; blank or «Any» drops it', async () => {
    const s = await setup({ status: 'voided' });
    await s.openIt();
    await ionValue(s.field('total_min').element, '12,50', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ status: 'voided', total_min: '12,50' });
    await s.wrapper.setProps({ modelValue: s.emitted().at(-1) });
    await ionValue(s.field('status').element, '');
    expect(s.emitted().at(-1)).toEqual({ total_min: '12,50' });
    await s.wrapper.setProps({ modelValue: s.emitted().at(-1) });
    s.wrapper.findComponent(PaymentMethodPicker).vm.$emit('update:modelValue', 'Cash');
    await s.wrapper.vm.$nextTick();
    expect(s.emitted().at(-1)).toEqual({ total_min: '12,50', payment_method_name: 'Cash' });
  });

  it('an amount that is not one is marked under its field', async () => {
    const s = await setup({ total_max: 'abc' });
    await s.openIt();
    expect(prop(s.field('total_max').element, 'errorText')).toBe('Type an amount, like 12.50');
    expect(s.field('total_max').classes()).toContain('ion-invalid');
    expect(s.find('sales-filters').attributes('data-invalid')).toBe('true');
  });

  it('what the server refused shows under its filter', async () => {
    const s = await setup({ date_from: '2026-13-01' }, { fieldErrors: { date_from: 'Not a date.' } });
    await s.openIt();
    expect(prop(s.field('date_from').element, 'errorText')).toBe('Not a date.');
  });

  it('«Clear» drops them all; «Done» closes', async () => {
    const s = await setup({ status: 'voided', total_min: '5' });
    await s.openIt();
    await click(s.find('sales-filters-clear').element);
    expect(s.emitted().at(-1)).toEqual({});
    await click(s.find('sales-filters-done').element);
    expect(s.field('status').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ status: 'refunded' }, {}, 'es');
    expect(s.find('sales-filters').text()).toContain('Filtros');
    expect(s.find('sales-filters').attributes('aria-label')).toBe('Filtros: 1 en uso');
    await s.openIt();
    expect(s.find('sales-filters-panel').attributes('aria-label')).toBe('Filtrar ventas');
    expect(s.field('status').findAll('ion-select-option').map((o) => o.text())).toEqual(['Cualquiera', 'Completada', 'Anulada', 'Devuelta']);
    expect(prop(s.field('total_min').element, 'label')).toBe('Total desde');
    expect([s.find('sales-filters-clear').text(), s.find('sales-filters-done').text()]).toEqual(['Limpiar', 'Hecho']);
  });
});
