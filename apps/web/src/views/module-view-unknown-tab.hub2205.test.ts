// @vitest-environment happy-dom
//
// hub#2205 — an address INSIDE an app that the app does not have lands on «This page does not
// exist», the same screen a wrong address at the root gets (hub#1723).
//
// What was seen recording the manual (24-25/09): `/m/customers/esta-no-existe` painted the
// customer list as if the address were valid, while the root answered `/esta-no-existe` with the
// 404 screen. hub#1723 had made this case swap to the app's first tab with a passing toast — a
// toast is gone in three seconds, so the recorded frames showed a valid-looking list, and two
// wrong addresses still answered two different ways.
//
// The market answers a sub-address it does not have the way it answers any other: Shopify admin
// (`/admin/products/nope`), Stripe, Square Dashboard and Odoo show their «page not found» and keep
// the address in the bar. So the swap is gone: the bar keeps the wrong address (the evidence of
// the bad link), the app says so with the SAME heading, body and way out as the root 404, and the
// app's own tabbar stays under it — the module's menu, as the shell's menu stays around the root
// 404 — so the right screen is one tap away.
//
// `/m/sales` with NO tab at all is not that case and must keep opening the first tab in silence:
// it is the address the launcher, «My apps» and /apps all use.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, reactive } from 'vue';

// Reactive, so a change of address re-runs ModuleView's route watcher the way the router does.
const routeParams = reactive<{ moduleId: string; navId?: string }>({ moduleId: 'sales', navId: 'list' });
const replaceSpy = vi.fn();

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId ?? ''}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId ?? ''}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: replaceSpy }),
}));

const { toastInfoSpy } = vi.hoisted(() => ({ toastInfoSpy: vi.fn() }));
vi.mock('../lib/toast', () => ({
  toastInfo: toastInfoSpy,
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

/** The tabs this module really has. Everything else in the address bar is a wrong guess. */
const POS_TAB = {
  moduleId: 'sales',
  moduleName: 'Sales',
  nav: { id: 'pos', label: 'Sell', icon: 'cart' },
};
const HISTORY_TAB = {
  moduleId: 'sales',
  moduleName: 'Sales',
  nav: { id: 'history', label: 'History', icon: 'time' },
};

vi.mock('../lib/module-loader', () => ({
  loadMenu: vi.fn(async () => [POS_TAB, HISTORY_TAB]),
  loadManifest: vi.fn(async () => ({})),
  loadComponent: vi.fn(async () => 'erp-sales-pos'),
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
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ModuleView from './ModuleView.vue';
import { loadComponent } from '../lib/module-loader';
import { IonSegment } from '@ionic/vue';
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
  return { wrapper, t: i18n.global.t };
}

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
}

beforeEach(() => {
  routeParams.moduleId = 'sales';
  routeParams.navId = 'list';
  replaceSpy.mockReset();
  toastInfoSpy.mockReset();
  vi.mocked(loadComponent).mockClear();
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

describe('a screen this app does not have says so (hub#2205)', () => {
  it('lands on «This page does not exist» instead of painting another tab', async () => {
    const { wrapper } = mountModuleView();
    await settle();

    const state = wrapper.find('[data-testid="not-found"]');
    expect(state.exists(), 'an unknown tab still paints another screen of the app').toBe(true);
    expect(state.attributes('heading')).toBe(enCatalogue.notFound.title);
    expect(state.attributes('message')).toBe(enCatalogue.notFound.body);
    expect(wrapper.find('[data-testid="not-found-home"]').text()).toBe(enCatalogue.notFound.action);
    expect(wrapper.html()).not.toContain('notFound.');
  });

  it('says it in Spanish too', async () => {
    const { wrapper } = mountModuleView('es');
    await settle();

    const state = wrapper.find('[data-testid="not-found"]');
    expect(state.attributes('heading')).toBe(esCatalogue.notFound.title);
    expect(state.attributes('message')).toBe(esCatalogue.notFound.body);
  });

  it('keeps the wrong address in the bar and mounts no screen of the app', async () => {
    mountModuleView();
    await settle();

    // A replace rewrites the bar and destroys the evidence that the link was wrong (hub#1723).
    expect(replaceSpy).not.toHaveBeenCalled();
    expect(loadComponent).not.toHaveBeenCalled();
    expect(toastInfoSpy).not.toHaveBeenCalled();
  });

  it('keeps the app tabbar under it, with no tab claiming to be on screen', async () => {
    const { wrapper } = mountModuleView();
    await settle();

    const segment = wrapper.findComponent(IonSegment);
    expect(segment.exists(), 'the way to the real screens of the app is gone').toBe(true);
    expect(segment.props('value') ?? '').toBe('');
  });

  it('treats a synthetic tab the app does not declare as unknown too', async () => {
    // `settings` and the Plan tab are painted by the shell only when the manifest brings the
    // block; without it they are addresses like any other the app does not have.
    routeParams.navId = 'settings';
    const { wrapper } = mountModuleView();
    await settle();

    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(true);
    expect(replaceSpy).not.toHaveBeenCalled();
  });

  it('takes the previous tab off screen when the address moves to one the app does not have', async () => {
    routeParams.navId = 'pos';
    const { wrapper } = mountModuleView();
    await settle();
    expect(wrapper.find('erp-sales-pos').exists()).toBe(true);

    routeParams.navId = 'list';
    await settle();

    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(true);
    // Hidden is not gone: a till left mounted under the 404 keeps listening and working.
    expect(wrapper.find('erp-sales-pos').exists(), 'the previous tab is still mounted').toBe(false);
    // And the tabbar stops claiming «Sell» is on screen.
    expect(wrapper.findComponent(IonSegment).props('value') ?? '').toBe('');
  });

  // The controls. Without them the fix is «404 on every app open».
  it('paints the tab when the address names one the app has', async () => {
    routeParams.navId = 'pos';
    const { wrapper } = mountModuleView();
    await settle();

    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(false);
    expect(loadComponent).toHaveBeenCalledTimes(1);
    expect(toastInfoSpy).not.toHaveBeenCalled();
    expect(replaceSpy).not.toHaveBeenCalled();
  });

  it('opens the first tab in silence when the address names NO tab at all', async () => {
    routeParams.navId = undefined;
    const { wrapper } = mountModuleView();
    await settle();

    // `/m/sales` claims no screen, so being taken to the first one is the app opening.
    expect(wrapper.find('[data-testid="not-found"]').exists()).toBe(false);
    expect(replaceSpy).toHaveBeenCalledWith('/m/sales/pos');
    expect(toastInfoSpy).not.toHaveBeenCalled();
  });
});
