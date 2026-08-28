// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1175 — a module the entitlement names BLOCKED must say so on
// screen, not report itself as empty.
//
// The router half of hub#1175 lets `/m/<id>` MOUNT when `isModuleBlocked(id)` is true, on the
// promise that `ModuleView` paints its `blocked-card` («why you cannot open this»). But the exact
// module of the report — `invoice_series`, retired from the marketplace, hence absent from the
// entitled ids AND present in `revalidation.blocked_modules` — contributes NO tabs: `loadMenu()`
// drops every module that is not entitled (`lib/module-loader.ts`, gate §2.10). With no entry to
// mount, `mount()` landed in the EMPTY state — «Nothing to show here yet… check it is active in
// Apps» — which is the wrong sentence: the module is active, the entitlement is what stops it.
// The card only renders under `status === 'ready'`, so a blocked module with nothing to mount has
// to be `ready` (with the card) and never `empty`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';

const routeParams = { moduleId: 'invoice_series', navId: 'list' };

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

/** The menu call, under the test's control: each mount takes the next queued answer. */
const menuAnswers: Array<() => Promise<unknown>> = [];
vi.mock('../lib/module-loader', () => ({
  loadMenu: () => (menuAnswers.shift() ?? (() => Promise.resolve([])))(),
  loadManifest: vi.fn(async () => ({ name: 'Invoice series' })),
  loadComponent: vi.fn(async () => 'erp-invoice-series-list'),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ forModule: () => ({}), on: () => () => {} }),
}));
vi.mock('../lib/protects', () => ({ resolveProtectsGuard: vi.fn(async () => null) }));

/** What the entitlement says about the module under test — the knob of this file. */
const blocked = new Set<string>();
vi.mock('../lib/entitlement', () => ({
  isModuleBlocked: (id: string) => blocked.has(id),
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/immersive', () => ({
  chromeControlsFor: () => [],
  installChrome: () => () => {},
}));
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

/** One nav entry of ANOTHER module: the menu answered, and has nothing for the one under test. */
const otherModuleEntry = () => ({
  moduleId: 'invoice',
  moduleName: 'Invoices',
  nav: { id: 'list', label: 'Invoices', icon: 'receipt' },
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

beforeEach(() => {
  menuAnswers.length = 0;
  blocked.clear();
});

describe('a module the entitlement names BLOCKED explains itself on screen (hub#1175)', () => {
  it('paints the blocked-card, not the empty state, when the blocked module has no tab to mount', async () => {
    blocked.add('invoice_series');
    menuAnswers.push(async () => [otherModuleEntry()]);
    const wrapper = mountModuleView();
    await settle();

    const card = wrapper.find('.blocked-card');
    expect(card.exists(), 'a blocked module with no tabs paints no blocked-card').toBe(true);
    expect(card.text()).toContain(enCatalogue.moduleView.blockedTitle);
    // «Nothing to show here… check it is active in Apps» is the wrong sentence here: the module
    // IS active; the entitlement is what stops it.
    expect(wrapper.find('ok-empty-state').exists(), 'the empty state is shown instead').toBe(false);
    expect(wrapper.find('ok-inline-feedback').exists(), 'the error state is shown too').toBe(false);
  });

  it('says it in Spanish too', async () => {
    blocked.add('invoice_series');
    menuAnswers.push(async () => [otherModuleEntry()]);
    const wrapper = mountModuleView('es');
    await settle();

    expect(wrapper.find('.blocked-card').text()).toContain(esCatalogue.moduleView.blockedTitle);
  });

  it('keeps the empty state for a module nobody blocked (hub#1169 stays true)', async () => {
    menuAnswers.push(async () => [otherModuleEntry()]);
    const wrapper = mountModuleView();
    await settle();

    expect(wrapper.find('ok-empty-state').exists()).toBe(true);
    expect(wrapper.find('.blocked-card').exists()).toBe(false);
  });
});
