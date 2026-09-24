// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1797 — coming back to a screen that is already mounted, with
// only the part after `?` (or `#`) changed, must not rebuild the module's Web Component.
//
// The case that bit: a salon has the till open, goes to the agenda and taps «Charge» on an
// appointment. The agenda pushes `/m/sales/pos?appointment_id=…` and fires `popstate` — the module
// contract for a deep link (flows#57, sales#279) — so the till that is ALREADY mounted (hidden by
// Ionic, still alive) serves the appointment. Then Ionic brings that same page back on screen, and
// `onIonViewWillEnter` compared `fullPath` (query included): `/m/sales/pos` ≠
// `/m/sales/pos?appointment_id=…`, so it ran `mount()` and replaced the till with a brand-new copy.
// Two tills raced — the old one opening the appointment's order, the new one listing open orders —
// and depending on which answer arrived first the till came up empty.
//
// The screen is identified by its PATH. A query/hash change on a mounted screen is served by the
// module through `popstate`; a PATH change while hidden still has to rebuild (the control below).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, reactive } from 'vue';

const route = reactive({
  params: { moduleId: 'sales', navId: 'pos' } as Record<string, string>,
  name: 'module',
  path: '/m/sales/pos',
  fullPath: '/m/sales/pos',
});

/** Moves the fake router the way vue-router does: path, params and fullPath together. */
function navigate(moduleId: string, navId: string, suffix = ''): void {
  route.params = { moduleId, navId };
  route.path = `/m/${moduleId}/${navId}`;
  route.fullPath = `${route.path}${suffix}`;
}

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

/** Ionic's page lifecycle, captured so the test can play «leave» and «come back». */
const lifecycle: { willEnter: Array<() => void>; didLeave: Array<() => void> } = {
  willEnter: [],
  didLeave: [],
};
vi.mock('@ionic/vue', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    onIonViewWillEnter: (fn: () => void) => lifecycle.willEnter.push(fn),
    onIonViewDidLeave: (fn: () => void) => lifecycle.didLeave.push(fn),
  };
});

const loadMenu = vi.fn(async () => [
  { moduleId: 'sales', moduleName: 'Sales', nav: { id: 'pos' } },
  { moduleId: 'sales', moduleName: 'Sales', nav: { id: 'orders' } },
]);
vi.mock('../lib/module-loader', () => ({
  loadMenu: () => loadMenu(),
  loadManifest: vi.fn(async () => ({})),
  loadComponent: vi.fn(async (entry: { nav: { id: string } }) => `erp-sales-${entry.nav.id}`),
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

const mounted: Array<{ unmount: () => void }> = [];

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
}

async function mountTill(suffix = '') {
  navigate('sales', 'pos', suffix);
  lifecycle.willEnter.length = 0;
  lifecycle.didLeave.length = 0;
  loadMenu.mockClear();
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: enCatalogue } });
  const wrapper = mount(ModuleView, { global: { plugins: [i18n] } });
  mounted.push(wrapper);
  await settle();
  return wrapper;
}

/** The module's element currently in the outlet. */
function moduleElement(wrapper: ReturnType<typeof mount>): Element | null {
  return wrapper.element.querySelector('[class*="outlet"] > *, erp-sales-pos, erp-sales-orders');
}

/** Ionic hides this page (another one pushed on top), then brings it back. */
async function leaveAndComeBack(whileAway: () => void): Promise<void> {
  lifecycle.didLeave.forEach((fn) => fn());
  whileAway();
  await settle();
  lifecycle.willEnter.forEach((fn) => fn());
  await settle();
}

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

describe('coming back with only the query changed keeps the mounted module (hub#1797)', () => {
  it('hub1797_charge_from_agenda_keeps_the_same_till_instead_of_building_a_second_one', async () => {
    const wrapper = await mountTill();
    const till = moduleElement(wrapper);
    expect(till?.tagName.toLowerCase(), 'the till never mounted').toBe('erp-sales-pos');
    const loadsBefore = loadMenu.mock.calls.length;

    await leaveAndComeBack(() => navigate('sales', 'pos', '?appointment_id=apt-1'));

    // 🔴 The defect: a second till replaced the first while the first was serving the booking.
    expect(moduleElement(wrapper), 'the till was rebuilt').toBe(till);
    expect(till && wrapper.element.contains(till), 'the first till was dropped').toBe(true);
    expect(loadMenu.mock.calls.length, 'the screen was mounted again').toBe(loadsBefore);
  });

  it('a hash-only change on the way back keeps the mounted module too', async () => {
    const wrapper = await mountTill();
    const till = moduleElement(wrapper);

    await leaveAndComeBack(() => navigate('sales', 'pos', '#split'));

    expect(moduleElement(wrapper)).toBe(till);
  });

  it('a till first opened FROM the agenda is not rebuilt when it comes back without the query', async () => {
    // The mirror case: the first mount already carried `?appointment_id=` (cold «Charge»). What
    // this copy remembers is the screen, not the link it was opened with.
    const wrapper = await mountTill('?appointment_id=apt-1');
    const till = moduleElement(wrapper);

    await leaveAndComeBack(() => navigate('sales', 'pos'));

    expect(moduleElement(wrapper)).toBe(till);
  });

  it('a different tab reached while hidden is still rebuilt on the way back', async () => {
    // The control: comparing by path must not freeze a screen whose PATH moved without it.
    const wrapper = await mountTill();
    const till = moduleElement(wrapper);

    await leaveAndComeBack(() => navigate('sales', 'orders'));

    const now = moduleElement(wrapper);
    expect(now?.tagName.toLowerCase()).toBe('erp-sales-orders');
    expect(now).not.toBe(till);
  });
});
