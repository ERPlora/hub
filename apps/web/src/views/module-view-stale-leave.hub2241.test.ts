// @vitest-environment happy-dom
// Regression test for ERPlora/hub#2241 (born as ERPlora/staff#73) — going A → B → A quickly left
// the app screen on its loading skeleton forever, with its data already loaded.
//
// Measured on the real shell (hub:stable 1.1.30 + staff, API answers 400 ms late): Staff → Roles →
// Staff tapped before the page animation ends got stuck 4 times out of 4; Staff and staying there,
// 0 out of 3. The cause is the ORDER in which Ionic Vue calls this view's lifecycle hooks:
// `IonRouterOutlet.handlePageTransition` fires `onIonViewWillEnter` BEFORE awaiting the outlet's
// `commit()`, and `ion-router-outlet` runs commits one at a time. So on the way back the view hears
//
//   WillLeave(A) … WillEnter(A)  ← the way back
//                  DidLeave(A)   ← the way OUT, arriving late
//                  DidEnter(A)
//
// and `onIonViewDidLeave` (hub#1099/#1797) took that late «you left» at its word: it cancelled the
// mount in flight, emptied the outlet and marked the copy off screen — on the page the user is
// looking at. Nothing mounts it again until the next navigation.
//
// The hooks are fired here in that measured order, straight from the arrays Ionic Vue reads
// (`instance.proxy.onIonView*`), with a reactive route so the view's own route watcher runs too.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';

const shared = vi.hoisted(() => ({
  route: null as null | {
    params: { moduleId: string; navId: string };
    name: string;
    path: string;
    fullPath: string;
  },
}));

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue');
  shared.route = reactive({
    params: { moduleId: 'staff', navId: 'staff' },
    name: 'module',
    path: '/m/staff/staff',
    fullPath: '/m/staff/staff',
  });
  return {
    useRoute: () => shared.route,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  };
});

const MENU = [
  { moduleId: 'staff', moduleName: 'Staff', nav: { id: 'staff', label: 'Staff', component: 'erp-staff-members' } },
  { moduleId: 'staff', moduleName: 'Staff', nav: { id: 'roles', label: 'Roles', component: 'erp-staff-roles' } },
];

/** Menu answers the test holds back, the way a slow hub does. Empty → answer at once. */
const heldMenus: Array<() => void> = [];
let holdMenus = false;
vi.mock('../lib/module-loader', () => ({
  loadMenu: () =>
    new Promise((resolve) => {
      if (holdMenus) heldMenus.push(() => resolve(MENU));
      else resolve(MENU);
    }),
  loadManifest: vi.fn(async () => ({})),
  loadComponent: async (entry: { nav: { component: string } }) => entry.nav.component,
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

type Hook = 'onIonViewWillEnter' | 'onIonViewDidEnter' | 'onIonViewWillLeave' | 'onIonViewDidLeave';

/** Calls the view's Ionic hooks exactly as `IonRouterOutlet`'s `fireLifecycle` does. */
function fire(wrapper: VueWrapper, hook: Hook): void {
  const proxy = (wrapper.vm as unknown as { $: { proxy: Record<string, unknown> } }).$.proxy;
  for (const h of (proxy[hook] as Array<() => void> | undefined) ?? []) h();
}

function goTo(navId: string): void {
  const route = shared.route!;
  route.params.navId = navId;
  route.path = `/m/staff/${navId}`;
  route.fullPath = `/m/staff/${navId}`;
}

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
}

const mounted: VueWrapper[] = [];

function mountStaff(): VueWrapper {
  const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: enCatalogue } });
  const wrapper = mount(ModuleView, { global: { plugins: [i18n] }, attachTo: document.body });
  mounted.push(wrapper);
  return wrapper;
}

beforeEach(() => {
  holdMenus = false;
  heldMenus.length = 0;
  goTo('staff');
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

describe('a late «you left» does not strand the screen on show (hub#2241)', () => {
  it('hub2241_staff_roles_staff_tapped_fast_ends_on_the_staff_list_not_the_skeleton', async () => {
    const wrapper = mountStaff();
    await settle();
    fire(wrapper, 'onIonViewDidEnter');
    expect(wrapper.find('[data-testid="module-skeleton"]').exists(), 'first visit never loaded').toBe(false);
    expect(wrapper.find('.outlet erp-staff-members').exists()).toBe(true);

    // The hub answers slowly from here on.
    holdMenus = true;
    // Tap «Roles»: Ionic announces the way out, the route moves.
    fire(wrapper, 'onIonViewWillLeave');
    goTo('roles');
    await settle();
    // …and «Staff» again before the page animation ended: the route comes back, and Ionic Vue
    // announces the way BACK before it delivers the way OUT.
    goTo('staff');
    await settle();
    fire(wrapper, 'onIonViewWillEnter');
    fire(wrapper, 'onIonViewDidLeave'); // the way out, late
    fire(wrapper, 'onIonViewDidEnter');
    await settle();

    // The slow hub answers everything it owed.
    holdMenus = false;
    while (heldMenus.length) heldMenus.shift()!();
    await settle();

    // 🔴 The defect: the page on show stayed on its skeleton, with nothing left to mount it.
    expect(wrapper.find('[data-testid="module-skeleton"]').exists(), 'the screen on show is stuck loading').toBe(false);
    expect(wrapper.find('.outlet erp-staff-members').exists(), 'the staff list never came back').toBe(true);
  });

  it('hub2241_a_real_way_out_still_lets_the_module_go', async () => {
    // hub#1797 must survive: a copy that DID leave (no way back announced after its way out) still
    // releases its module, so a hidden screen never keeps serving deep links.
    const wrapper = mountStaff();
    await settle();
    fire(wrapper, 'onIonViewDidEnter');
    expect(wrapper.find('.outlet erp-staff-members').exists()).toBe(true);

    fire(wrapper, 'onIonViewWillLeave');
    fire(wrapper, 'onIonViewDidLeave');
    await settle();
    expect(wrapper.find('.outlet').element.children.length, 'the hidden copy kept its module').toBe(0);

    // And coming back mounts it again (hub#1797's own promise).
    fire(wrapper, 'onIonViewWillEnter');
    fire(wrapper, 'onIonViewDidEnter');
    await settle();
    expect(wrapper.find('.outlet erp-staff-members').exists()).toBe(true);
  });
});
