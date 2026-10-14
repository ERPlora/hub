// The filters of the customer list (CUSTOMER-F02): stage, source, active and spent by range («From /
// To», in euros). A «Filters» button with the count of filters in use opens them; a change applies
// at once; «Clear» drops them all. The query takes cents: `filterParams` turns euros into cents.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountCustomer } from '../__tests__/mount-customer';
import CustomerFilters, { type CustomerFilterValues, filterParams, filtersInUse } from './CustomerFilters.vue';
import source from './CustomerFilters.vue?raw';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(initial: CustomerFilterValues = {}, locale: 'en' | 'es' = 'en') {
  const values = ref<CustomerFilterValues>(initial);
  const Host = defineComponent({
    setup: () => () =>
      h(CustomerFilters, { modelValue: values.value, 'onUpdate:modelValue': (v: CustomerFilterValues) => (values.value = v) }),
  });
  const m = await mountCustomer(Host, { locale, attachTo: document.body });
  const el = (id: string) => document.querySelector<HTMLElement & { value?: unknown }>(`[data-testid="${id}"]`);
  async function open() {
    el('customer-filters')!.click();
    await flush();
  }
  async function choose(id: string, value: string) {
    el(id)!.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  async function type(id: string, value: string) {
    el(id)!.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  return { ...m, values, el, open, choose, type };
}

describe('the «Filters» button', () => {
  it('is small, as the other buttons of the toolbar', async () => {
    const s = await setup();
    expect(s.el('customer-filters')!.getAttribute('size')).toBe('small');
  });
});

describe('CustomerFilters', () => {
  it('is a «Filters» button; it opens stage, source, active and spent from/to', async () => {
    const s = await setup();
    expect(s.el('customer-filters')!.textContent).toContain('Filters');
    expect(s.el('customer-filters-count')).toBeNull();
    await s.open();
    for (const id of ['stage', 'source', 'active', 'spent-from', 'spent-to']) expect(s.el(`customer-filter-${id}`), id).not.toBeNull();
    const stage = s.el('customer-filter-stage')!;
    expect([...stage.querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'Any',
      'Lead',
      'Prospect',
      '1st purchase',
      'Active',
      'At risk',
      'Dormant',
      'Churned',
      'VIP',
    ]);
    expect([...s.el('customer-filter-active')!.querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'Any',
      'Active',
      'Not active',
    ]);
  });

  it('applies each change at once and counts the filters in use; «Any» or blank drops one', async () => {
    const s = await setup();
    await s.open();
    await s.choose('customer-filter-stage', 'vip');
    await s.type('customer-filter-spent-from', '10,5');
    expect(s.values.value).toEqual({ lifecycle_stage: 'vip', spent_from: '10,5' });
    expect(s.el('customer-filters-count')?.textContent?.trim()).toBe('2');
    await s.choose('customer-filter-stage', '');
    expect(s.values.value).toEqual({ spent_from: '10,5' });
  });

  it('reads «1.000» as a thousand euros', async () => {
    const s = await setup();
    await s.open();
    await s.type('customer-filter-spent-from', '1.000');
    expect(filterParams(s.values.value)).toEqual({ spent_min: 100000 });
    expect(s.el('customer-filters-count')?.textContent?.trim()).toBe('1');
  });

  it('an amount it cannot read is said under its field and neither counts nor filters', async () => {
    const s = await setup();
    await s.open();
    await s.type('customer-filter-spent-to', 'mil');
    const field = s.el('customer-filter-spent-to') as HTMLElement & { errorText?: string };
    expect(field.errorText).toBe('Write an amount, like 1.000,50.');
    expect(field.classList.contains('ion-invalid')).toBe(true);
    expect(s.el('customer-filters-count')).toBeNull();
    expect(filterParams(s.values.value)).toEqual({});
    expect(filtersInUse(s.values.value)).toBe(0);
  });

  it('«Clear» drops them all', async () => {
    const s = await setup({ lifecycle_stage: 'vip', is_active: 'true' });
    await s.open();
    s.el('customer-filters-clear')!.click();
    await flush();
    expect(s.values.value).toEqual({});
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.el('customer-filters')!.textContent).toContain('Filtros');
    await s.open();
    expect((s.el('customer-filter-spent-from') as HTMLElement & { label?: string }).label).toBe('Gastado desde (€)');
  });

  it('has no OutfitKit tag and every filled control declares mode="md"', () => {
    expect(source).not.toMatch(/<ok[-]/);
    for (const tag of source.match(/<ion-(input|select)\b[^>]*>/gs) ?? []) if (/fill=/.test(tag)) expect(tag).toMatch(/mode="md"/);
  });
});

describe('filterParams', () => {
  it('turns the filters into the query: a yes/no for active, cents for spent', () => {
    expect(filterParams({ lifecycle_stage: 'vip', source: 'import', is_active: 'false', spent_from: '10,5', spent_to: '100' })).toEqual({
      lifecycle_stage: 'vip',
      source: 'import',
      is_active: false,
      spent_min: 1050,
      spent_max: 10000,
    });
  });

  it('leaves out what is not in use or not an amount', () => {
    expect(filterParams({})).toEqual({});
    expect(filterParams({ spent_from: 'abc' })).toEqual({});
  });
});
