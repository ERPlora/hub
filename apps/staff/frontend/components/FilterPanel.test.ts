// The column filters of a staff list (WORKBOOK «Pantallas»: Staff by first name, last name, email,
// phone, role, status, bookable, hire date, colour and user; Roles by status, colour and members;
// Time Off by member, type, status, full day and dates). The old table opened them in its side panel
// from a funnel button with a count; here the same button opens a dialog with one control per filter:
// a text box, a closed list with «Any», a long list searched on the server (members, roles, accounts:
// a picker with «Any» first), or a from–to range of numbers or of dates. Every change applies
// at once (the list asks the server again); «Clear» drops them all and «Done» closes.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountStaff } from '../__tests__/mount-staff';
import FilterPanel, { type FilterSpec } from './FilterPanel.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const FILTERS: FilterSpec[] = [
  { kind: 'text', key: 'email', label: 'Email' },
  {
    kind: 'select',
    key: 'status',
    label: 'Status',
    options: [
      { value: 'active', label: 'Active' },
      { value: 'inactive', label: 'Inactive' },
    ],
  },
  { kind: 'range', key: 'hire', label: 'Hire date', keys: ['hire_date_from', 'hire_date_to'], type: 'date' },
  { kind: 'range', key: 'members', label: 'Members', keys: ['member_count_min', 'member_count_max'] },
  {
    kind: 'search',
    key: 'user_id',
    label: 'Hub user',
    load: async (search: string) => [{ value: '4', label: 'Ana López' }].filter((o) => o.label.toLowerCase().includes(search.toLowerCase())),
  },
];

type Control = HTMLElement & { label?: string; value?: unknown; type?: string; fill?: string };

async function setup(modelValue: Record<string, string> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountStaff(FilterPanel, { props: { filters: FILTERS, modelValue, testid: 'staff-members' }, locale });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: Record<string, string>) => m.wrapper.setProps({ modelValue: value }) });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map((e) => e[0]);
  const open = async () => click(m.find('staff-members-filters').element);
  return { ...m, emitted, open };
}

describe('FilterPanel', () => {
  it('is a «Filters» button with the funnel, without a count while nothing filters', async () => {
    const s = await setup();
    const button = s.find('staff-members-filters');
    expect(button.element.tagName).toBe('ION-BUTTON');
    expect(button.text()).toContain('Filters');
    expect(s.find('staff-members-filters-count').exists()).toBe(false);
    expect(button.attributes('aria-label')).toBe('Filters');
  });

  it('counts the filters in use, a range once, and says so to screen readers', async () => {
    const s = await setup({ status: 'active', hire_date_from: '2024-01-01', hire_date_to: '2024-12-31', email: '' });
    expect(s.find('staff-members-filters-count').text()).toBe('2');
    expect(s.find('staff-members-filters').attributes('aria-label')).toBe('Filters: 2');
  });

  it('opens a dialog with one boxed control per filter; a date range has date fields', async () => {
    const s = await setup({ status: 'inactive' });
    await s.open();
    const email = s.inDoc('staff-members-filter-email') as Control;
    expect([email.tagName, email.label, email.getAttribute('mode'), email.fill]).toEqual(['ION-INPUT', 'Email', 'md', 'outline']);
    const status = s.inDoc('staff-members-filter-status') as Control;
    expect([status.tagName, status.label, status.value]).toEqual(['ION-SELECT', 'Status', 'inactive']);
    expect([...status.querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual(['Any', 'Active', 'Inactive']);
    const from = s.inDoc('staff-members-filter-hire_date_from') as Control;
    const to = s.inDoc('staff-members-filter-hire_date_to') as Control;
    expect([from.label, from.type, to.label, to.type]).toEqual(['Hire date · From', 'date', 'Hire date · To', 'date']);
    expect((s.inDoc('staff-members-filter-member_count_min') as Control).type).toBe('number');
  });

  it('applies every change at once; «Any» or blank drops it', async () => {
    const s = await setup();
    await s.open();
    await ionValue(s.inDoc('staff-members-filter-email'), 'ana', 'ionInput');
    await ionValue(s.inDoc('staff-members-filter-status'), 'active');
    await ionValue(s.inDoc('staff-members-filter-hire_date_from'), '2024-01-01', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ email: 'ana', status: 'active', hire_date_from: '2024-01-01' });
    await ionValue(s.inDoc('staff-members-filter-status'), '');
    await ionValue(s.inDoc('staff-members-filter-email'), '  ', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ hire_date_from: '2024-01-01' });
  });

  it('a long list is a picker searched on the server, «Any» first; the choice is kept by its name', async () => {
    const s = await setup();
    await s.open();
    const picker = s.inDoc('staff-members-filter-user_id') as Control;
    expect([picker.tagName, picker.label, picker.value]).toEqual(['ION-INPUT', 'Hub user', 'Any']);
    await click(picker);
    const root = (s.wrapper.element.parentElement ?? s.wrapper.element) as Element;
    const options = [...root.querySelectorAll('[data-testid="staff-members-filter-user_id-option"]')];
    expect(options.map((o) => [o.getAttribute('data-value'), o.textContent?.trim()])).toEqual([
      ['', 'Any'],
      ['4', 'Ana López'],
    ]);
    await click(options[1]);
    expect(s.emitted().at(-1)).toEqual({ user_id: '4' });
    expect((s.inDoc('staff-members-filter-user_id') as Control).value).toBe('Ana López');
    expect(s.find('staff-members-filters-count').text()).toBe('1');
  });

  it('«Clear» drops them all; «Done» closes', async () => {
    const s = await setup({ status: 'active' });
    await s.open();
    await click(s.inDoc('staff-members-filters-clear'));
    expect(s.emitted().at(-1)).toEqual({});
    await click(s.inDoc('staff-members-filters-done'));
    expect(s.inDoc('staff-members-filter-email')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.find('staff-members-filters').text()).toContain('Filtros');
    await s.open();
    expect([...(s.inDoc('staff-members-filter-status') as Control).querySelectorAll('ion-select-option')][0].textContent?.trim()).toBe('Cualquiera');
  });
});
