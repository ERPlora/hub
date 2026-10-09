// @vitest-environment happy-dom
// hub#2500 — the record of somebody who signs in with a PIN only never offers administration.
//
// The sign-up already refused it (hub#355, `local_cannot_administer`); editing the record let it
// through, and from then on that PIN opened an administrator session. The hub now refuses it on the
// edit too (HUB-F148), and the record says so before saving: the administrator roles are not in the
// list until the person has an email to be invited with (HUB_SHELL-F84). The address typed in
// «My profile» is not that email, so it is not pre-filled as if it were.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const { replace, push } = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'marta' } }),
  useRouter: () => ({ replace, push }),
  onBeforeRouteLeave: () => {},
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));
vi.mock('../lib/badge-scanner', () => ({ onBadgeScan: () => () => {} }));
vi.mock('../lib/nfc-badge', () => ({ nfcBadgeReady: { value: false } }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import EmployeeFormPage from './EmployeeFormPage.vue';

const ROLES = ['admin', 'manager', 'employee'].map((name) => ({
  name,
  label: name,
  extends: name,
  source: 'base',
  active: true,
  permissions: 0,
}));

function person(overrides: Record<string, unknown>) {
  return {
    id: 'marta',
    name: 'Marta Ruiz',
    email: '',
    role: 'employee',
    cloud_user_id: null,
    is_active: true,
    has_pin: true,
    has_badge: false,
    created_at: '2026-10-01T10:00:00Z',
    ...overrides,
  };
}

/** The runtime: one person in the census, the three base roles, and every PUT recorded. */
function runtimeWith(marta: Record<string, unknown>) {
  const puts: Array<Record<string, unknown>> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        puts.push(JSON.parse(String(init.body)));
        return { ok: true, status: 200, json: async () => ({ ok: true, data: marta }) };
      }
      const data = String(url).includes('/api/hub/roles') ? ROLES : [marta];
      return { ok: true, status: 200, json: async () => ({ ok: true, data }) };
    }),
  );
  return puts;
}

async function mountForm(locale: 'en' | 'es' = 'es') {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, es } });
  const wrapper = mount(EmployeeFormPage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  }) as unknown as ReturnType<typeof mount> & {
    vm: { form: Record<string, unknown>; onSave: () => Promise<void> };
  };
  await flushPromises();
  return wrapper;
}

function offeredRoles(form: ReturnType<typeof mount>): string[] {
  return form.findAllComponents(IonSelectOption).map((o) => String(o.props('value')));
}

function emailInput(form: ReturnType<typeof mount>) {
  const input = form.findAllComponents(IonInput).find((i) => i.attributes('data-testid') === 'employee-email');
  if (!input) throw new Error('the record has no email field');
  return input;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('the record of a PIN-only person never offers administration (hub#2500)', () => {
  it('leaves the administrator role out while the person has no account', async () => {
    runtimeWith(person({ has_account: false }));
    const form = await mountForm();

    expect(offeredRoles(form)).not.toContain('admin');
    expect(offeredRoles(form)).toEqual(expect.arrayContaining(['manager', 'employee']));
  });

  it('offers it again once an email to invite them with is typed', async () => {
    runtimeWith(person({ has_account: false }));
    const form = await mountForm();

    form.vm.form.email = 'marta@example.com';
    await flushPromises();

    expect(offeredRoles(form)).toContain('admin');
  });

  it('offers it to a person who already signs in with an account', async () => {
    runtimeWith(person({ has_account: true, email: 'marta@example.com', has_pin: false }));
    const form = await mountForm();

    expect(offeredRoles(form)).toContain('admin');
  });

  it('does not pass the address typed in «My profile» off as the access email', async () => {
    runtimeWith(person({ has_account: false, email: 'ioan@example.com' }));
    const form = await mountForm();

    expect(form.vm.form.email).toBe('');
    expect(offeredRoles(form)).not.toContain('admin');
    expect(emailInput(form).props('helperText')).toBe(es.employeeForm.pinOnlyEmailHelp);
  });

  it('refuses to save administration without an account, in the field, before the hub', async () => {
    const puts = runtimeWith(person({ has_account: false }));
    const form = await mountForm();

    form.vm.form.role = 'admin';
    await form.vm.onSave();
    await flushPromises();

    expect(puts).toEqual([]);
    // Under the role, where it is fixed: the select carries it as its error text.
    const role = form.findAllComponents(IonSelect).find((s) => s.attributes('data-testid') === 'employee-role');
    expect(role?.props('errorText')).toBe(es.employeeForm.errors.local_cannot_administer);
  });

  it('keeps every other edit of that person working', async () => {
    const puts = runtimeWith(person({ has_account: false, email: 'ioan@example.com' }));
    const form = await mountForm();

    form.vm.form.role = 'manager';
    form.vm.form.name = 'Marta Ruiz López';
    await form.vm.onSave();
    await flushPromises();

    expect(puts).toHaveLength(1);
    expect(puts[0]).toMatchObject({ role: 'manager', name: 'Marta Ruiz López' });
    expect(puts[0]).not.toHaveProperty('email');
  });

  it('keeps the role of a record that is already an administrator, so it can still be lowered', async () => {
    // Written before this guard existed: the hub still lets it be renamed or given a lower role.
    runtimeWith(person({ has_account: false, role: 'admin' }));
    const form = await mountForm();

    expect(form.vm.form.role).toBe('admin');
    expect(offeredRoles(form)).toContain('admin');
  });

  it('has the help line in English too', async () => {
    runtimeWith(person({ has_account: false }));
    const form = await mountForm('en');

    expect(emailInput(form).props('helperText')).toBe(en.employeeForm.pinOnlyEmailHelp);
  });

  it('changes nothing against a runtime that does not say who has an account', async () => {
    // A runtime older than hub#2500 sends no `has_account`: nothing is hidden, the hub decides.
    runtimeWith(person({ email: 'marta@example.com' }));
    const form = await mountForm();

    expect(form.vm.form.email).toBe('marta@example.com');
    expect(offeredRoles(form)).toContain('admin');
  });
});
