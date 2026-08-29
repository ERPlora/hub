// @vitest-environment happy-dom
// Follow-up regression for ERPlora/hub#1302: the same defect family as the setup-screen text —
// a PIN digit count that disagrees with THIS hub's `pin_length` — was also sitting in the PIN
// `ion-input`'s `maxlength`. Both `EmployeeFormPage.vue` (detail edit, `/employees/:id`) and
// `EmployeesPage.vue` (inline add form in Personal) hardcoded `:maxlength="8"`, a leftover from
// the pre-hub#974 "between 4 and 8 digits" validation. THIS hub's PIN is always exactly 4 or 6
// digits (`hubPinLength`, `lib/pin-length.ts`), so the field must never accept more than that —
// typing a 7th or 8th digit into a 6-length hub's PIN was accepted by the input even though
// `clean_pin` would always refuse it.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonInput } from '@ionic/vue';

import es from '../i18n/locales/es';
import { hubSettings } from '../lib/hub-settings';

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, hash: '' }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  onBeforeRouteLeave: () => {},
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));
vi.mock('../lib/badge-scanner', () => ({ onBadgeScan: () => () => {} }));
vi.mock('../lib/nfc-badge', () => ({ nfcBadgeReady: { value: false } }));

import EmployeeFormPage from './EmployeeFormPage.vue';
import EmployeesPage from './EmployeesPage.vue';

/** Every fetch this pair of screens can make resolves to an empty, successful envelope. */
function stubEmptyFetch(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, data: [] }) })),
  );
}

function mountWithI18n<T>(component: T) {
  const i18n = createI18n({ legacy: false, locale: 'es', fallbackLocale: 'es', messages: { es } });
  return mount(component as never, { global: { plugins: [i18n], renderStubDefaultSlot: true } });
}

/** The ONE ion-input labelled «PIN local» — same label on both screens, found only once each. */
function pinInputOf(wrapper: VueWrapper) {
  const input = wrapper.findAllComponents(IonInput).find((i) => i.props('label') === es.employeeForm.pin);
  if (!input) throw new Error(`no hay ningún campo etiquetado «${es.employeeForm.pin}»`);
  return input;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  stubEmptyFetch();
  hubSettings.value = null;
});

describe("hub#1302 — the PIN field never accepts more digits than THIS hub's PIN length", () => {
  it.each([6, 4])('EmployeeFormPage caps the PIN input at exactly %d digits (pin_length)', async (n) => {
    hubSettings.value = { pin_length: n } as never;
    const wrapper = mountWithI18n(EmployeeFormPage);
    await flushPromises();

    expect(pinInputOf(wrapper as VueWrapper).props('maxlength')).toBe(n);
  });

  it.each([6, 4])('EmployeesPage caps the inline PIN input at exactly %d digits (pin_length)', async (n) => {
    hubSettings.value = { pin_length: n } as never;
    const wrapper = mountWithI18n(EmployeesPage);
    await flushPromises();

    expect(pinInputOf(wrapper as VueWrapper).props('maxlength')).toBe(n);
  });
});
