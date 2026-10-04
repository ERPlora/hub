// @vitest-environment happy-dom
// hub#2444 — from Employees → Roles, a link to System → Updates opened System → Resources.
//
// Ionic keeps Employees mounted after leaving it and `useRoute()` is the app's one route: its
// tab ↔ hash sync read `#updates` as an unknown Employees tab, fell back to «Staff» and wrote
// `#staff` onto the System address, which System then read as its default tab. The pattern guard
// (`tabbed-pages-own-their-address.hub2444.test.ts`) keeps every tabbed page on `useHashTab`; this
// is the symptom itself, on a real page. Harness from `pin-maxlength-not-hardcoded.hub1302.test.ts`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonSegment } from '@ionic/vue';

import en from '../i18n/locales/en';

const { route, replace } = await vi.hoisted(async () => {
  const vue = await import('vue');
  const route = vue.reactive({ path: '/employees', hash: '#roles', params: {} });
  const replace = vi.fn((to: { path?: string; hash?: string }) => {
    if (to.path !== undefined) route.path = to.path;
    if (to.hash !== undefined) route.hash = to.hash;
    return Promise.resolve();
  });
  return { route, replace };
});

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, push: vi.fn() }),
  onBeforeRouteLeave: () => {},
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));
vi.mock('../lib/badge-scanner', () => ({ onBadgeScan: () => () => {} }));
vi.mock('../lib/nfc-badge', () => ({ nfcBadgeReady: { value: false } }));

import EmployeesPage from './EmployeesPage.vue';

// Every page shares the ONE route: a page left mounted by a previous test would still react to it.
const mounted: Array<{ unmount: () => void }> = [];
afterEach(() => mounted.splice(0).forEach((w) => w.unmount()));

async function mountEmployees() {
  const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en } });
  const wrapper = mount(EmployeesPage, { global: { plugins: [i18n], renderStubDefaultSlot: true } });
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
}

const shownTab = (wrapper: Awaited<ReturnType<typeof mountEmployees>>) =>
  wrapper.findComponent(IonSegment).props('value');

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ ok: true, data: [] }) })),
  );
  route.path = '/employees';
  route.hash = '#roles';
  replace.mockClear();
});

describe('Employees → a link to a System tab', () => {
  it('lands on the System tab it names, untouched by Employees', async () => {
    const wrapper = await mountEmployees();
    expect(shownTab(wrapper)).toBe('roles');

    route.path = '/system';
    route.hash = '#updates';
    await flushPromises();

    expect(replace).not.toHaveBeenCalled();
    expect(route.hash).toBe('#updates');
    // And Employees did not flip itself behind the scenes: back on it, Roles is still there.
    expect(shownTab(wrapper)).toBe('roles');
  });

  it('still follows its own address: a link to another Employees tab opens it', async () => {
    const wrapper = await mountEmployees();
    route.hash = '#staff';
    await flushPromises();
    expect(shownTab(wrapper)).toBe('staff');
    expect(replace).not.toHaveBeenCalled();
  });
});
