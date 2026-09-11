// @vitest-environment happy-dom
//
// hub#1723 (the comment on the issue) — the SAME silent fallback, one floor down.
//
// What was seen on `banco-pre` (v1.1.19): `/m/sales/list` — an address that does not exist, the
// sales list lives inside the POS's «Ventas» tab — painted the «Vender» screen of the till with
// nothing said. So the silent bounce was never only the shell's catch-all towards Inicio: a nav
// id this module does not have quietly became a different screen of the same module.
//
// The canonisation itself STAYS, and on purpose: it is what keeps an old bookmark (a tab that was
// renamed between versions) working instead of dying, and it is what stops the address bar from
// claiming a tab while another one is on screen. What was missing is the sentence — the same
// half-fix hub#1175 already made for a module id the entitlement never named, which used to bounce
// to Inicio in silence and now says why.
//
// `/m/sales` with NO tab at all is not that case and must stay mute: nobody claimed a screen
// there, so there is nothing to correct. That is the control this file exists to hold.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';

const routeParams: { moduleId: string; navId?: string } = { moduleId: 'sales', navId: 'list' };
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

/** The ONE tab this module really has. Everything else in the address bar is a wrong guess. */
const POS_TAB = {
  moduleId: 'sales',
  moduleName: 'Sales',
  nav: { id: 'pos', label: 'Sell', icon: 'cart' },
};

vi.mock('../lib/module-loader', () => ({
  loadMenu: vi.fn(async () => [POS_TAB]),
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
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

describe('a screen this app does not have says so (hub#1723)', () => {
  it('still opens the tab it does have, so an old bookmark keeps working', async () => {
    mountModuleView();
    await settle();

    expect(replaceSpy).toHaveBeenCalledWith('/m/sales/pos');
  });

  it('but no longer does it in silence: it names the screen it opened instead', async () => {
    const { t } = mountModuleView();
    await settle();

    expect(toastInfoSpy, 'the wrong address is still swapped without a word').toHaveBeenCalledTimes(1);
    expect(toastInfoSpy).toHaveBeenCalledWith(t('moduleView.unknownTabToast', { tab: 'Sell' }));
    // The sentence has to carry the tab that IS on screen; a bare «that does not exist» leaves
    // the person wondering what they are looking at now.
    expect(String(toastInfoSpy.mock.calls[0][0])).toContain('Sell');
    expect(String(toastInfoSpy.mock.calls[0][0])).not.toContain('moduleView.');
  });

  it('says it in Spanish too', async () => {
    const { t } = mountModuleView('es');
    await settle();

    expect(toastInfoSpy).toHaveBeenCalledWith(t('moduleView.unknownTabToast', { tab: 'Sell' }));
    expect(esCatalogue.moduleView.unknownTabToast).not.toBe(enCatalogue.moduleView.unknownTabToast);
  });

  // The two controls. Without them the fix is «toast on every module open», which is noise on the
  // busiest screen of the product — and noise is how a warning that matters stops being read.
  it('says nothing when the address names the tab it really opens', async () => {
    routeParams.navId = 'pos';
    mountModuleView();
    await settle();

    expect(toastInfoSpy).not.toHaveBeenCalled();
    expect(replaceSpy).not.toHaveBeenCalled();
  });

  it('says nothing when the address names NO tab at all, which is how every app opens', async () => {
    routeParams.navId = undefined;
    mountModuleView();
    await settle();

    // `/m/sales` is the address the launcher, «Mis apps» and /apps all use. It claims no screen,
    // so being taken to the first one is not a correction — it is the app opening.
    expect(replaceSpy).toHaveBeenCalledWith('/m/sales/pos');
    expect(toastInfoSpy).not.toHaveBeenCalled();
  });
});
