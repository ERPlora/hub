// The column filters of a schedule list (WORKBOOK «Pantallas · Días especiales»: special days by date
// from–to, name, status and yearly; overrides by their from and to dates, reason and status). The old
// table opened them in its side panel from a funnel button with a count; here the same button opens a
// dialog with one control per filter: a text box, a closed list with «Any», or a from–to range of
// dates. Every change applies at once (the list asks the server again); «Clear» drops them all.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountSchedule } from '../__tests__/mount-schedule';
import FilterPanel, { type FilterSpec } from './FilterPanel.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const FILTERS: FilterSpec[] = [
  { kind: 'text', key: 'name', label: 'Name' },
  {
    kind: 'select',
    key: 'is_closed',
    label: 'Status',
    options: [
      { value: 'true', label: 'Closed' },
      { value: 'false', label: 'Open' },
    ],
  },
  { kind: 'range', key: 'date', label: 'Date', keys: ['date_from', 'date_to'] },
];

type Control = HTMLElement & { label?: string; value?: unknown; type?: string; fill?: string; mode?: string };

async function setup(modelValue: Record<string, string> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSchedule(FilterPanel, { props: { filters: FILTERS, modelValue, testid: 'schedule-special-days' }, locale });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: Record<string, string>) => m.wrapper.setProps({ modelValue: value }) });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map((e) => e[0]);
  const open = async () => click(m.find('schedule-special-days-filters').element);
  const control = (key: string) => m.find(`schedule-special-days-filter-${key}`).element as Control;
  return { ...m, emitted, open, control };
}

describe('FilterPanel', () => {
  it('is a «Filters» button with the funnel, without a count while nothing filters', async () => {
    const s = await setup();
    const button = s.find('schedule-special-days-filters');
    expect(button.element.tagName).toBe('ION-BUTTON');
    expect(button.text()).toContain('Filters');
    expect(s.find('schedule-special-days-filters-count').exists()).toBe(false);
  });

  it('counts the filters in use, a range once', async () => {
    const s = await setup({ is_closed: 'true', date_from: '2026-01-01', date_to: '2026-12-31' });
    expect(s.find('schedule-special-days-filters-count').text()).toBe('2');
    expect(s.find('schedule-special-days-filters').attributes('aria-label')).toBe('Filters: 2');
  });

  it('opens one boxed control per filter, a date range as two date fields', async () => {
    const s = await setup();
    await s.open();
    expect(s.find('schedule-special-days-filters-panel').exists()).toBe(true);
    expect([s.control('name').tagName, s.control('is_closed').tagName]).toEqual(['ION-INPUT', 'ION-SELECT']);
    expect([s.control('date_from').type, s.control('date_to').type]).toEqual(['date', 'date']);
    expect([s.control('date_from').label, s.control('date_to').label]).toEqual(['Date · From', 'Date · To']);
    expect([s.control('name').fill, s.control('name').getAttribute('mode')]).toEqual(['outline', 'md']);
  });

  it('applies each change at once; blank or «Any» drops the filter; «Clear» drops them all', async () => {
    const s = await setup({ name: 'xmas' });
    await s.open();
    await ionValue(s.control('is_closed'), 'false');
    expect(s.emitted().at(-1)).toEqual({ name: 'xmas', is_closed: 'false' });
    await ionValue(s.control('date_from'), '2026-12-01', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ name: 'xmas', is_closed: 'false', date_from: '2026-12-01' });
    await ionValue(s.control('name'), '  ', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ is_closed: 'false', date_from: '2026-12-01' });
    await click(s.find('schedule-special-days-filters-clear').element);
    expect(s.emitted().at(-1)).toEqual({});
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.find('schedule-special-days-filters').text()).toContain('Filtros');
  });
});
