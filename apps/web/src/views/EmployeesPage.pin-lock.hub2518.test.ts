// @vitest-environment happy-dom
// hub#2518 — the PIN doors of Employees (create a person, edit their record) now spend the
// editor's budget of tries, like changing one's own PIN (hub#2499): past it, the hub answers
// `429 too_many_attempts` with `retry_after_secs` instead of saying whether the number is taken.
//
// That refusal is a PLATFORM one — `{ok:false, error:"…", code, retry_after_secs}`, the code at the
// top and the sentence a Spanish string the server wrote — so the screens' `hub.users.*` ladder did
// not see it and painted that sentence as it came. What is pinned here: both places a PIN is typed
// in Employees say, in the hub's language, how many minutes to wait.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';
import en from '../i18n/locales/en';

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/employees', hash: '', params: {} }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  onBeforeRouteLeave: () => {},
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/toast', () => ({ toast: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/badge-scanner', () => ({ onBadgeScan: () => () => {} }));
vi.mock('../lib/nfc-badge', () => ({ nfcBadgeReady: { value: false } }));
vi.mock('../lib/device', () => ({ getDeviceContext: async () => ({}) }));

import EmployeesPage from './EmployeesPage.vue';
import EmployeeFormPage from './EmployeeFormPage.vue';

/** The sentence the server writes into the refusal; a hub in English must not show it. */
const SERVER_SENTENCE = 'demasiados intentos fallidos: espera unos minutos';

/** Empty census; every write is refused with the lock, `retry_after_secs` as given. */
function runtimeLockingPinWrites(retryAfterSecs?: number): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST' || init?.method === 'PUT') {
        return {
          ok: false,
          status: 429,
          json: async () => ({
            ok: false,
            error: SERVER_SENTENCE,
            code: 'too_many_attempts',
            ...(retryAfterSecs === undefined ? {} : { retry_after_secs: retryAfterSecs }),
          }),
        };
      }
      return { ok: true, status: 200, json: async () => ({ ok: true, data: [] }) };
    }),
  );
}

function i18nIn(locale: 'es' | 'en') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'es',
    missingWarn: false,
    fallbackWarn: false,
    messages: { es, en },
  });
}

const mounted: Array<{ unmount: () => void }> = [];
afterEach(() => mounted.splice(0).forEach((w) => w.unmount()));
beforeEach(() => vi.unstubAllGlobals());

type Vm = { vm: { form: Record<string, unknown> } & Record<string, unknown> };

/** Employees › Personal: the «New» panel, a local person with a PIN. */
async function createFromThePanel(locale: 'es' | 'en') {
  const wrapper = mount(EmployeesPage, { global: { plugins: [i18nIn(locale)], renderStubDefaultSlot: true } });
  mounted.push(wrapper);
  await flushPromises();
  const vm = (wrapper as unknown as Vm).vm;
  Object.assign(vm.form, { name: 'Pau Gil', role: 'employee', pin: '8246', local: true });
  await (vm.createUser as () => Promise<void>)();
  await flushPromises();
  return wrapper;
}

/** The person form: save with a PIN. */
async function saveTheForm(locale: 'es' | 'en') {
  const wrapper = mount(EmployeeFormPage, { global: { plugins: [i18nIn(locale)], renderStubDefaultSlot: true } });
  mounted.push(wrapper);
  await flushPromises();
  const vm = (wrapper as unknown as Vm).vm;
  Object.assign(vm.form, { name: 'Pau Gil', role: 'employee', local: true, pin: '8246' });
  await (vm.onSave as () => Promise<void>)();
  await flushPromises();
  return wrapper;
}

describe('Employees: the PIN lock says how long to wait (hub#2518)', () => {
  for (const [door, act] of [
    ['the «New» panel', createFromThePanel],
    ['the person form', saveTheForm],
  ] as const) {
    it(`${door}: in Spanish, with the minutes rounded up`, async () => {
      runtimeLockingPinWrites(200);
      const page = await act('es');

      expect(page.text()).toContain(
        'Demasiados cambios de PIN en poco tiempo. Espera 4 minutos y vuelve a intentarlo.',
      );
      expect(page.text()).not.toContain(SERVER_SENTENCE);
    });

    it(`${door}: in English, never the server's Spanish sentence`, async () => {
      runtimeLockingPinWrites(60);
      const page = await act('en');

      expect(page.text()).toContain('Too many PIN changes in a short time. Wait 1 minute and try again.');
      expect(page.text()).not.toContain(SERVER_SENTENCE);
    });

    it(`${door}: without a wait in the refusal, «a few minutes»`, async () => {
      runtimeLockingPinWrites(undefined);
      const page = await act('es');

      expect(page.text()).toContain(es.employeeForm.pinTooManyAttemptsNoWait);
    });
  }
});
