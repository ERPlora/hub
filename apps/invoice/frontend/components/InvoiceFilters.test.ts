// The filters of the Invoices list (INVOICE-F16; the old column filters of status, type, date and total,
// plus series and source): the funnel button with the count of filters in use, opening a panel with
// Status, Type, Series, Source, Issued from–until and Total from–up to (euros). A change applies at once
// (the page asks the server again); «Clear filters» drops them all; «Done» closes. An amount that is not
// one is marked under its field; what the server refused (a 422 of the list) too.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountInvoice } from '../__tests__/mount-invoice';
import InvoiceFilters from './InvoiceFilters.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const prop = (el: Element, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

async function setup(modelValue: Record<string, string> = {}, extra: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(InvoiceFilters, { props: { modelValue, ...extra }, locale });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value);
  const openIt = () => click(m.find('invoice-filters').element);
  const field = (key: string) => m.find(`invoice-filter-${key}`);
  return { ...m, emitted, openIt, field };
}

describe('InvoiceFilters', () => {
  it('is the funnel button «Filters», with the count of filters in use (a range counts once)', async () => {
    const none = await setup();
    expect(none.find('invoice-filters').text()).toBe('Filters');
    expect(none.find('invoice-filters-count').exists()).toBe(false);
    const some = await setup({ status: 'paid', issue_date_from: '2026-10-01', issue_date_to: '2026-10-14' });
    expect(some.find('invoice-filters-count').text()).toBe('2');
    expect(some.find('invoice-filters').attributes('aria-label')).toBe('Filters: 2 in use');
  });

  it('opens «Filter invoices» with the closed lists already translated, the days and the totals', async () => {
    const s = await setup();
    await s.openIt();
    expect(s.find('invoice-filters-panel').attributes('aria-label')).toBe('Filter invoices');
    expect(s.field('status').findAll('ion-select-option').map((o) => o.text())).toEqual(['Any', 'Issued', 'Paid', 'Cancelled']);
    expect(s.field('invoice_type').findAll('ion-select-option').map((o) => o.text())).toEqual([
      'Any',
      'Invoice (F1)',
      'Ticket (F2)',
      'Invoice replacing a ticket (F3)',
      'Rectifying (R1)',
      'Rectifying (R2)',
      'Rectifying (R3)',
      'Rectifying (R4)',
      'Rectifying (R5)',
    ]);
    expect(s.field('source_type').findAll('ion-select-option').map((o) => o.text())[1]).toBe('POS sale');
    expect(
      ['series_code', 'issue_date_from', 'issue_date_to', 'total_amount_from', 'total_amount_to'].map((key) => prop(s.field(key).element, 'label')),
    ).toEqual(['Series', 'Issued from', 'Issued until', 'Total from (€)', 'Total up to (€)']);
    expect([prop(s.field('issue_date_from').element, 'type'), prop(s.field('total_amount_from').element, 'inputmode')]).toEqual(['date', 'decimal']);
    for (const key of ['status', 'issue_date_from', 'total_amount_to']) {
      expect([prop(s.field(key).element, 'fill'), s.field(key).attributes('mode') ?? prop(s.field(key).element, 'mode')]).toEqual(['outline', 'md']);
    }
  });

  it('a change applies at once, as a new value; blank or «Any» drops it', async () => {
    const s = await setup({ status: 'paid' });
    await s.openIt();
    await ionValue(s.field('total_amount_from').element, '12,50', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ status: 'paid', total_amount_from: '12,50' });
    await s.wrapper.setProps({ modelValue: s.emitted().at(-1) });
    await ionValue(s.field('status').element, '');
    expect(s.emitted().at(-1)).toEqual({ total_amount_from: '12,50' });
  });

  it('an amount that is not one is marked under its field, and what the server refused too', async () => {
    const s = await setup({ total_amount_to: 'abc', issue_date_from: '2026-13-01' }, { fieldErrors: { issue_date_from: 'Not a date.' } });
    await s.openIt();
    expect(prop(s.field('total_amount_to').element, 'errorText')).toBe('Type an amount, like 12.50');
    expect(s.field('total_amount_to').classes()).toContain('ion-invalid');
    expect(prop(s.field('issue_date_from').element, 'errorText')).toBe('Not a date.');
    expect(s.find('invoice-filters').attributes('data-invalid')).toBe('true');
  });

  it('«Clear filters» drops them all; «Done» closes', async () => {
    const s = await setup({ status: 'paid', total_amount_from: '5' });
    await s.openIt();
    await click(s.find('invoice-filters-clear').element);
    expect(s.emitted().at(-1)).toEqual({});
    await click(s.find('invoice-filters-done').element);
    expect(s.field('status').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ status: 'cancelled' }, {}, 'es');
    expect(s.find('invoice-filters').attributes('aria-label')).toBe('Filtros: 1 en uso');
    await s.openIt();
    expect(s.find('invoice-filters-panel').attributes('aria-label')).toBe('Filtrar facturas');
    expect(s.field('status').findAll('ion-select-option').map((o) => o.text())).toEqual(['Cualquiera', 'Emitida', 'Pagada', 'Cancelada']);
    expect([s.find('invoice-filters-clear').text(), s.find('invoice-filters-done').text()]).toEqual(['Quitar filtros', 'Hecho']);
  });
});
