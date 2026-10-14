// The closed-list filters of the Groups, Tags and Fields tables (WORKBOOK «Pantallas»: active; type,
// required and active): a «Filters» button with the count in use opens one select per filter, «Any»
// first; a change applies at once; «Clear» drops them all.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountCustomer } from '../__tests__/mount-customer';
import SelectFilters, { type SelectFilterSpec } from './SelectFilters.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
afterEach(() => {
  document.body.innerHTML = '';
});

const SPECS: SelectFilterSpec[] = [
  { key: 'is_active', label: 'Active', options: [{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }] },
  { key: 'field_type', label: 'Type', options: [{ value: 'text', label: 'Text' }] },
];

async function setup(initial: Record<string, string> = {}) {
  const values = ref<Record<string, string>>(initial);
  const Host = defineComponent({
    setup: () => () =>
      h(SelectFilters, {
        modelValue: values.value,
        'onUpdate:modelValue': (v: Record<string, string>) => (values.value = v),
        filters: SPECS,
        testid: 'customer-fields',
      }),
  });
  const m = await mountCustomer(Host, { attachTo: document.body });
  const el = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  return { ...m, values, el };
}

describe('the «Filters» button', () => {
  it('is small, as the other buttons of the toolbar', async () => {
    const s = await setup();
    expect(s.el('customer-fields-filters')!.getAttribute('size')).toBe('small');
  });
});

describe('SelectFilters', () => {
  it('a «Filters» button opens one select per filter, «Any» first', async () => {
    const s = await setup();
    expect(s.el('customer-fields-filters')!.textContent).toContain('Filters');
    s.el('customer-fields-filters')!.click();
    await flush();
    expect([...s.el('customer-fields-filter-is_active')!.querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual([
      'Any',
      'Yes',
      'No',
    ]);
    expect(s.el('customer-fields-filter-field_type')).not.toBeNull();
  });

  it('a change applies at once and is counted; «Any» drops it; «Clear» drops all', async () => {
    const s = await setup();
    s.el('customer-fields-filters')!.click();
    await flush();
    s.el('customer-fields-filter-is_active')!.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'false' } }));
    await flush();
    expect(s.values.value).toEqual({ is_active: 'false' });
    expect(s.el('customer-fields-filters-count')?.textContent?.trim()).toBe('1');
    s.el('customer-fields-filter-is_active')!.dispatchEvent(new CustomEvent('ionChange', { detail: { value: '' } }));
    await flush();
    expect(s.values.value).toEqual({});
    s.values.value = { is_active: 'true', field_type: 'text' };
    await flush();
    s.el('customer-fields-filters-clear')!.click();
    await flush();
    expect(s.values.value).toEqual({});
  });
});
