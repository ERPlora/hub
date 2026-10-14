// The column filters of a tax list (TAX-F01, F03, F13; the WORKBOOK's screens: Categories by Key, Name, Description and
// Origin; Rules by Country, Region, Category, Type, Qualification, Regime and %; Aliases by Alias,
// Category and Origin). The old table opened them in its side panel from a funnel button with a
// count; here the same button opens a dialog with one control per filter: a text box, a closed list
// with «Any», or a from–to range. Every change applies at once (the list asks the server again);
// «Clear» drops them all and «Done» closes.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountTax, settle } from '../__tests__/mount-tax';
import FilterPanel, { type FilterSpec } from './FilterPanel.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const FILTERS: FilterSpec[] = [
  { kind: 'text', key: 'region_code', label: 'Region', maxlength: 6 },
  {
    kind: 'select',
    key: 'country_code',
    label: 'Country',
    options: [
      { value: 'ES', label: 'Spain (ES)' },
      { value: 'PT', label: 'Portugal (PT)' },
    ],
  },
  { kind: 'range', key: 'rate', label: '%', keys: ['rate_min', 'rate_max'], min: 0, max: 100 },
];

async function setup(modelValue: Record<string, string> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTax(FilterPanel, { props: { filters: FILTERS, modelValue, testid: 'tax-rules' }, locale });
  // A parent's `v-model`: each new value comes back as the prop.
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: Record<string, string>) => m.wrapper.setProps({ modelValue: value }) });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map((e) => e[0]);
  const open = async () => click(m.find('tax-rules-filters').element);
  return { ...m, emitted, open };
}

describe('FilterPanel', () => {
  it('is a «Filters» button with the funnel, without a count while nothing filters', async () => {
    const s = await setup();
    const button = s.find('tax-rules-filters');
    expect(button.element.tagName).toBe('ION-BUTTON');
    expect(button.text()).toContain('Filters');
    expect(button.find('ion-icon').exists()).toBe(true);
    expect(s.find('tax-rules-filters-count').exists()).toBe(false);
    expect(button.attributes('aria-label')).toBe('Filters');
  });

  it('counts the filters in use, a range once, and says so to screen readers', async () => {
    const s = await setup({ country_code: 'ES', rate_min: '4', rate_max: '21', region_code: '' });
    expect(s.find('tax-rules-filters-count').text()).toBe('2');
    expect(s.find('tax-rules-filters').attributes('aria-label')).toBe('Filters: 2');
  });

  it('opens a dialog with one boxed control per filter, in order', async () => {
    const s = await setup({ country_code: 'PT' });
    await s.open();
    expect(s.inDoc('tax-rules-filters-panel')).not.toBeNull();
    // `fill` is a prop (a DOM property); `mode` is not one of Ionic Vue's proxies: an attribute.
    const region = s.inDoc('tax-rules-filter-region_code') as HTMLElement & { label?: string; fill?: string };
    expect([region.tagName, region.label, region.getAttribute('mode'), region.fill]).toEqual(['ION-INPUT', 'Region', 'md', 'outline']);
    const country = s.inDoc('tax-rules-filter-country_code') as HTMLElement & { value?: unknown; label?: string };
    expect([country.tagName, country.label, country.value]).toEqual(['ION-SELECT', 'Country', 'PT']);
    expect([...country.querySelectorAll('ion-select-option')].map((o) => [(o as HTMLElement & { value?: unknown }).value, o.textContent?.trim()])).toEqual([
      ['', 'Any'],
      ['ES', 'Spain (ES)'],
      ['PT', 'Portugal (PT)'],
    ]);
    const from = s.inDoc('tax-rules-filter-rate_min') as HTMLElement & { label?: string; type?: string };
    const to = s.inDoc('tax-rules-filter-rate_max') as HTMLElement & { label?: string; type?: string };
    expect([from.label, from.type, to.label]).toEqual(['% · From', 'number', '% · To']);
  });

  it('applies every change at once: a text, a choice, a bound; «Any» or blank drops it', async () => {
    const s = await setup();
    await s.open();
    await ionValue(s.inDoc('tax-rules-filter-region_code'), 'CN', 'ionInput');
    await ionValue(s.inDoc('tax-rules-filter-country_code'), 'ES');
    await ionValue(s.inDoc('tax-rules-filter-rate_min'), '10', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ region_code: 'CN', country_code: 'ES', rate_min: '10' });
    await ionValue(s.inDoc('tax-rules-filter-country_code'), '');
    await ionValue(s.inDoc('tax-rules-filter-region_code'), '  ', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ rate_min: '10' });
  });

  it('«Clear» drops every filter; «Done» closes the dialog', async () => {
    const s = await setup({ country_code: 'ES', region_code: 'CN' });
    await s.open();
    await click(s.inDoc('tax-rules-filters-clear'));
    expect(s.emitted().at(-1)).toEqual({});
    await click(s.inDoc('tax-rules-filters-done'));
    await settle();
    expect(s.inDoc('tax-rules-filter-country_code')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ country_code: 'ES' }, 'es');
    expect(s.find('tax-rules-filters').text()).toContain('Filtros');
    expect(s.find('tax-rules-filters').attributes('aria-label')).toBe('Filtros: 1');
    await s.open();
    expect(s.inDoc('tax-rules-filter-country_code')?.querySelector('ion-select-option')?.textContent?.trim()).toBe('Cualquiera');
    expect(s.inDoc('tax-rules-filters-clear')?.textContent?.trim()).toBe('Limpiar');
    expect(s.inDoc('tax-rules-filters-done')?.textContent?.trim()).toBe('Hecho');
  });
});

describe('FilterPanel: what the server takes, and what it refuses', () => {
  it('bounds each box as the schema does: a region of 6 characters, a % between 0 and 100', async () => {
    const s = await setup();
    await s.open();
    const region = s.inDoc('tax-rules-filter-region_code') as HTMLElement & { maxlength?: number };
    const from = s.inDoc('tax-rules-filter-rate_min') as HTMLElement & { min?: string | number; max?: string | number };
    expect([region.maxlength, Number(from.min), Number(from.max)]).toEqual([6, 0, 100]);
  });

  it('paints a refusal of the server under its filter, and the button says something is wrong', async () => {
    const s = await setup({ rate_min: '500' });
    await s.wrapper.setProps({ fieldErrors: { rate_min: 'Input should be less than or equal to 100' } });
    expect(s.find('tax-rules-filters').attributes('data-invalid')).toBe('true');
    await s.open();
    const from = s.inDoc('tax-rules-filter-rate_min') as HTMLElement & { errorText?: string };
    expect([from.errorText, from.classList.contains('ion-invalid')]).toEqual(['Input should be less than or equal to 100', true]);
    expect(s.inDoc('tax-rules-filter-region_code')?.classList.contains('ion-invalid')).toBe(false);
  });
});

describe('FilterPanel: a filter among many options (a searchable list)', () => {
  const searchable = (search?: (text: string) => void): FilterSpec[] => [
    {
      kind: 'search',
      key: 'tax_category_key',
      label: 'Category',
      options: [
        { value: 'restaurant.food', label: 'Restaurant — food (restaurant.food)' },
        { value: 'product.generic', label: 'Product — generic (product.generic)' },
      ],
      search,
    },
  ];

  it('opens the searchable list, «Any» first, and a choice filters', async () => {
    const m = await mountTax(FilterPanel, { props: { filters: searchable(), modelValue: {}, testid: 'tax-rules' } });
    await click(m.find('tax-rules-filters').element);
    await click(m.inDoc('tax-rules-filter-tax_category_key'));
    const options = m.wrapper.findAll('[data-testid="tax-rules-filter-tax_category_key-option"]');
    expect(options.map((o) => o.attributes('data-value'))).toEqual(['', 'restaurant.food', 'product.generic']);
    await click(options[2].element);
    expect(m.wrapper.emitted('update:modelValue')?.at(-1)).toEqual([{ tax_category_key: 'product.generic' }]);
  });

  it('with a server search, what is typed goes to the page', async () => {
    const asked: string[] = [];
    const m = await mountTax(FilterPanel, { props: { filters: searchable((text) => asked.push(text)), modelValue: {}, testid: 'tax-rules' } });
    await click(m.find('tax-rules-filters').element);
    await click(m.inDoc('tax-rules-filter-tax_category_key'));
    await ionValue(m.inDoc('tax-rules-filter-tax_category_key-search'), ' food ', 'ionInput');
    expect(asked).toEqual(['food']);
  });
});
