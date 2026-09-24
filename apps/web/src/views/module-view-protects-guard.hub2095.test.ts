// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2095 — when the `protects` guard fires (the till is protected and
// the cash register is closed), the screen the declaring module brings (`erp-cashregister-open`)
// must END UP IN THE DOM, inside `.protects-outlet`.
//
// The outlet only renders under `status === 'ready'`, and `mount()` flipped the status to `ready`
// AFTER trying to append the component: at that moment `protectsOutlet` was still `null`, the `if`
// skipped in silence, and the person saw an empty page with no way to open the register.
//
// The other ModuleView tests mock `resolveProtectsGuard` to `null`, so none of them mounts a guard.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';

const routeParams = { moduleId: 'sales', navId: 'pos' };

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const menu = [
  { moduleId: 'sales', moduleName: 'Sales', nav: { id: 'pos', label: 'POS', icon: 'cart' } },
  {
    moduleId: 'cash_register',
    moduleName: 'Cash register',
    nav: { id: 'dashboard', label: 'Cash register', icon: 'cash' },
  },
];
vi.mock('../lib/module-loader', () => ({
  loadMenu: vi.fn(async () => menu),
  loadManifest: vi.fn(async () => ({ name: 'Sales' })),
  loadComponent: vi.fn(async (entry: { moduleId: string }) =>
    entry.moduleId === 'cash_register' ? 'erp-cashregister-dashboard' : 'erp-sales-pos',
  ),
}));
const forModule = vi.fn((id: string) => ({ scope: id }));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ forModule, on: () => () => {} }),
}));

/** The guard under test: what `resolveProtectsGuard` answers for this route. */
let guardComponent: string | undefined = 'erp-cashregister-open';
vi.mock('../lib/protects', () => ({
  resolveProtectsGuard: vi.fn(async () => ({
    def: {
      route_setting: 'protected_pos_url',
      component: guardComponent,
      resume_on: 'cash_register.session_opened',
    },
    declaringModule: 'cash_register',
  })),
}));
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

const mounted: Array<{ unmount: () => void }> = [];

function mountModuleView() {
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue },
  });
  const wrapper = mount(ModuleView, { global: { plugins: [i18n] }, attachTo: document.body });
  mounted.push(wrapper);
  return wrapper;
}

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
}

beforeEach(() => {
  guardComponent = 'erp-cashregister-open';
  forModule.mockClear();
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

describe('the protects guard mounts the screen of the declaring module (hub#2095)', () => {
  it('appends the guard component inside .protects-outlet, scoped to the declaring module', async () => {
    const wrapper = mountModuleView();
    await settle();

    const outlet = wrapper.find('.protects-outlet');
    expect(outlet.exists(), 'the guard fired but its outlet is not on screen').toBe(true);
    const el = outlet.element.querySelector('erp-cashregister-open') as
      | (HTMLElement & { client?: unknown })
      | null;
    expect(el, 'the outlet is empty: the guard component was never appended').not.toBeNull();
    expect(el?.client).toEqual({ scope: 'cash_register' });
    // The protected screen itself must not mount behind it.
    expect(document.querySelector('erp-sales-pos')).toBeNull();
    // A component is there, so the shell's generic fallback card is not.
    expect(outlet.find('.blocked-card').exists()).toBe(false);
  });

  it('keeps the generic fallback card when the guard brings no component', async () => {
    guardComponent = undefined;
    const wrapper = mountModuleView();
    await settle();

    const outlet = wrapper.find('.protects-outlet');
    expect(outlet.exists()).toBe(true);
    expect(outlet.find('.blocked-card').text()).toContain(enCatalogue.moduleView.protectedTitle);
  });
});
