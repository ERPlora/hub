// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1743 — a dead wifi must not be reported as a dead module.
//
// What was on screen (QA on `banco-pre`, shell v1.1.19, Playwright `setOffline(true)`): the module
// screen failed to load and said «Comprueba que el módulo siga instalado y activo, y vuelve a
// intentarlo» with a Retry button. The sentence is about the MODULE — the one thing that was
// perfectly fine. The owner of the shop reads it and goes looking for an app nobody uninstalled,
// while the actual fault is that the router is down.
//
// The shell had no way to tell the two apart: `mount()` ended in a bare `catch {}` that threw the
// error away and set one single `error` state, so «the network is gone» and «this module has no
// screen to open» came out as the same sentence. What separates them is already in the failure —
// a fetch that never reached anybody is a `TypeError`, and `navigator.onLine` says so out loud —
// and the market settled the copy a long time ago: Toast and Square both say «no connection» and
// keep saying it, with a retry, until the network is back.
//
// The two states this file holds apart, because saying one meaning the other IS the defect:
//
//   • offline — nothing reached the hub. Say the connection is gone, offer the retry.
//   • module  — the hub answered and the screen still could not be built. That is the old
//     sentence, and it has to survive intact: this is not «always blame the network» either.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';

const routeParams = { moduleId: 'sales', navId: 'orders' };

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const menuAnswers: Array<() => Promise<unknown>> = [];
vi.mock('../lib/module-loader', () => ({
  loadMenu: () => (menuAnswers.shift() ?? (() => Promise.resolve([])))(),
  loadManifest: vi.fn(async () => ({})),
  loadComponent: vi.fn(async () => 'erp-sales-orders'),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ forModule: () => ({}), on: () => () => {} }),
}));
vi.mock('../lib/protects', () => ({ resolveProtectsGuard: vi.fn(async () => null) }));
vi.mock('../lib/entitlement', () => ({
  isModuleBlocked: () => false,
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

/** The browser's own way of saying it. The shell listens to these and to nothing else. */
function goOffline(): void {
  window.dispatchEvent(new Event('offline'));
}

function goOnline(): void {
  window.dispatchEvent(new Event('online'));
}

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

/** What a fetch that never reached anybody throws in every browser we ship on. */
function networkFailure(): TypeError {
  return new TypeError('Failed to fetch');
}

beforeEach(() => {
  menuAnswers.length = 0;
  goOnline();
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
  goOnline();
});

describe('a dead network is not a dead module (hub#1743)', () => {
  it('hub1743_says_the_connection_is_gone_instead_of_blaming_the_module', async () => {
    goOffline();
    menuAnswers.push(() => Promise.reject(networkFailure()));
    const wrapper = mountModuleView();
    await settle();

    const feedback = wrapper.find('ok-inline-feedback');
    expect(feedback.exists(), 'the failed load paints no error at all').toBe(true);
    expect(feedback.attributes('heading')).toBe(enCatalogue.moduleView.offlineTitle);
    expect(wrapper.text()).toContain(enCatalogue.moduleView.offlineHint);
    // 🔴 The defect itself: the module was never the problem, so its name must not be in the room.
    expect(wrapper.text()).not.toContain(enCatalogue.moduleView.loadErrorHint);
    expect(feedback.attributes('heading')).not.toBe(enCatalogue.moduleView.loadError);
    // The way back stays: this is the one failure that fixes itself.
    expect(wrapper.text()).toContain(enCatalogue.moduleView.retry);
  });

  it('reads the failure itself, not only the browser flag', async () => {
    // `navigator.onLine === true` is not a promise of connectivity — it is true on a laptop
    // attached to a router with no uplink, which is the commonest way a shop loses the internet.
    // A fetch that comes back as a `TypeError` never reached anybody, and that is the fact.
    goOnline();
    menuAnswers.push(() => Promise.reject(networkFailure()));
    const wrapper = mountModuleView();
    await settle();

    expect(wrapper.find('ok-inline-feedback').attributes('heading')).toBe(
      enCatalogue.moduleView.offlineTitle,
    );
  });

  it('🔴 still blames the module when the hub DID answer', async () => {
    // The other half, and the reason this is not «always say the network is down»: an error the
    // runtime sent back is a real module failure and keeps its own sentence.
    goOnline();
    menuAnswers.push(() => Promise.reject(new Error('module manifest is not readable')));
    const wrapper = mountModuleView();
    await settle();

    const feedback = wrapper.find('ok-inline-feedback');
    expect(feedback.attributes('heading')).toBe(enCatalogue.moduleView.loadError);
    expect(wrapper.text()).toContain(enCatalogue.moduleView.loadErrorHint);
    expect(wrapper.text()).not.toContain(enCatalogue.moduleView.offlineHint);
  });

  it('says the offline state in Spanish too', async () => {
    goOffline();
    menuAnswers.push(() => Promise.reject(networkFailure()));
    const wrapper = mountModuleView('es');
    await settle();

    expect(wrapper.find('ok-inline-feedback').attributes('heading')).toBe(
      esCatalogue.moduleView.offlineTitle,
    );
    expect(wrapper.text()).toContain(esCatalogue.moduleView.offlineHint);
  });

  it('clears itself the moment the network comes back, without anybody pressing anything', async () => {
    // Toast and Square both recover on their own. A screen that stays wrong after the wifi is back
    // teaches people that the message means nothing.
    goOffline();
    menuAnswers.push(() => Promise.reject(networkFailure()));
    const wrapper = mountModuleView();
    await settle();
    expect(wrapper.find('ok-inline-feedback').attributes('heading')).toBe(
      enCatalogue.moduleView.offlineTitle,
    );

    menuAnswers.push(async () => [
      { moduleId: 'sales', moduleName: 'Sales', nav: { id: 'orders', label: 'Orders', icon: 'cart' } },
    ]);
    goOnline();
    await settle();

    expect(wrapper.find('ok-inline-feedback').exists(), 'the error survived the network').toBe(false);
  });
});
