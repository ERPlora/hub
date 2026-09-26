// @vitest-environment happy-dom
//
// hub#2190 — an app this hub does NOT have must not be announced as installed.
//
// What was seen recording the manual (25-26/09, free-plan hub with the hair-salon template):
// `/m/online_booking/bookings` ended on «This module is installed but has no screens to open right
// now», while Apps → My apps did not list it and the catalogue did not offer it. The screen
// contradicted Apps: the shell's EMPTY state (hub#1169) was written for an app that is installed
// and switched off, and it was also being said about an app that is not there at all, because the
// menu answers both cases the same way — no entry for that id.
//
// The market answers «you opened an app you do not have» by saying so and pointing at where you
// get it: Shopify admin («This app isn't installed» + Visit the App Store), Square and Odoo (the app
// page offers Install). So the two cases get two sentences: the runtime's installed list decides,
// an app it does not list says «This app is not installed» with the way to the catalogue, and an
// installed one that paints nothing keeps «Check it is active in Apps».
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';

const routeParams = { moduleId: 'online_booking', navId: 'bookings' };

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

/** What the runtime says is installed (`GET /api/modules`), under each test's control. */
const { installed } = vi.hoisted(() => ({
  installed: { answer: (): Promise<unknown[]> => Promise.resolve([]) },
}));

vi.mock('../lib/module-loader', () => ({
  // The menu only ever carries OTHER apps: nothing here has an entry for `online_booking`.
  loadMenu: vi.fn(async () => [
    { moduleId: 'sales', moduleName: 'Sales', nav: { id: 'pos', label: 'Sell', icon: 'cart' } },
  ]),
  loadManifest: vi.fn(async () => null),
  loadComponent: vi.fn(async () => 'erp-sales-pos'),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ forModule: () => ({}), on: () => () => {} }),
  listInstalledModules: () => installed.answer(),
}));
vi.mock('../lib/protects', () => ({ resolveProtectsGuard: vi.fn(async () => null) }));
vi.mock('../lib/entitlement', () => ({
  isModuleBlocked: () => false,
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/immersive', () => ({ chromeControlsFor: () => [], installChrome: () => () => {} }));
vi.mock('@erplora/outfitkit/tabbar', () => ({ scrollActiveTabIntoView: vi.fn() }));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/ModulePlanPanel.vue', () => ({
  default: { name: 'ModulePlanPanel', template: '<div />' },
}));
vi.mock('../components/ModuleSettingsForm.vue', () => ({
  default: { name: 'ModuleSettingsForm', template: '<div />' },
}));
vi.mock('../components/HubIcon.vue', () => ({
  default: { name: 'HubIcon', template: '<span />' },
}));

import ModuleView from './ModuleView.vue';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const mounted: Array<{ unmount: () => void }> = [];

function mountModuleView(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(ModuleView, { global: { plugins: [i18n] } });
  mounted.push(wrapper);
  return wrapper;
}

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
}

const SALES = { id: 'sales', name: 'Sales', version: '1.0.0', status: 'active' };

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

beforeEach(() => {
  installed.answer = () => Promise.resolve([SALES]);
});

describe('an app the hub does not have is not called installed (hub#2190)', () => {
  it('🔴 says «not installed» and points at the catalogue when the runtime does not list it', async () => {
    const wrapper = mountModuleView();
    await settle();

    const state = wrapper.find('[data-testid="module-not-installed"]');
    expect(state.exists(), 'an app this hub does not have is still painted as installed').toBe(true);
    expect(state.attributes('heading')).toBe(enCatalogue.moduleView.notInstalledTitle);
    expect(state.attributes('message')).toBe(enCatalogue.moduleView.notInstalledHint);
    // The contradiction itself must be gone, not merely joined by a second sentence.
    expect(wrapper.find('[data-testid="module-empty"]').exists()).toBe(false);
    expect(wrapper.html()).not.toContain(enCatalogue.moduleView.emptyHint);

    // Its one way out: the catalogue tab of Apps, where an app you do not have is installed.
    const action = wrapper.find('[data-testid="module-not-installed-catalog"]');
    expect(action.exists(), 'no way to the catalogue').toBe(true);
    // Ionic Vue reads the `router-link` prop; happy-dom shows it as the lower-cased attribute.
    expect(action.attributes('routerlink')).toBe('/apps#all');
    expect(action.text()).toBe(enCatalogue.moduleView.notInstalledAction);
  });

  it('says it in Spanish too', async () => {
    const wrapper = mountModuleView('es');
    await settle();

    const state = wrapper.find('[data-testid="module-not-installed"]');
    expect(state.attributes('heading')).toBe(esCatalogue.moduleView.notInstalledTitle);
    expect(state.attributes('message')).toBe(esCatalogue.moduleView.notInstalledHint);
    expect(wrapper.find('[data-testid="module-not-installed-catalog"]').text()).toBe(
      esCatalogue.moduleView.notInstalledAction,
    );
  });

  it('keeps «installed but nothing to open» for an app that IS installed and switched off', async () => {
    installed.answer = () =>
      Promise.resolve([SALES, { id: 'online_booking', name: 'Online booking', version: '1.0.0', status: 'inactive' }]);
    const wrapper = mountModuleView();
    await settle();

    expect(wrapper.find('[data-testid="module-empty"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="module-not-installed"]').exists()).toBe(false);
  });

  it('does not claim either sentence when it could not ask the runtime what is installed', async () => {
    installed.answer = () => Promise.reject(new Error('modules → 500'));
    const wrapper = mountModuleView();
    await settle();

    expect(wrapper.find('[data-testid="module-empty"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="module-not-installed"]').exists()).toBe(false);
    const feedback = wrapper.find('ok-inline-feedback');
    expect(feedback.exists(), 'a failed question paints no error').toBe(true);
    expect(feedback.attributes('heading')).toBe(enCatalogue.moduleView.loadError);
  });
});
