// @vitest-environment happy-dom
//
// hub#2353 — with the app in English, the tabs at the bottom of a module stayed in Spanish
// («Todos» instead of «All» in Tickets) while everything else around them was in English.
//
// The labels are translated BY THE RUNTIME (`/api/navigation?locale=`, ADR-0055): the language is
// baked into the answer. The shell boots in its default `es` and only applies the user's language
// once `/api/profile` answers, so a module opened on a cold start fetched its tabs in Spanish. The
// sidebar asks again on `erplora:locale-changed` (hub#781); the module screen did not, so its
// tabbar and its heading kept the Spanish answer until the next navigation.
//
// The module's own Web Component must NOT be remounted to fix that: it repaints itself on the same
// event, and remounting a till would throw away the ticket being rung up.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick, reactive } from 'vue';

const routeParams = reactive<{ moduleId: string; navId?: string }>({ moduleId: 'tickets', navId: 'all' });

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId ?? ''}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId ?? ''}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

/** What `/api/navigation?locale=<lang>` answers for this module, per language. */
const NAV: Record<string, { moduleName: string; labels: [string, string] }> = {
  es: { moduleName: 'Incidencias', labels: ['Todos', 'Acuerdos'] },
  en: { moduleName: 'Tickets', labels: ['All', 'Agreements'] },
};

vi.mock('../lib/module-loader', async () => {
  const { getLocale } = await import('../i18n');
  return {
    // Like the real one: the language is the one active WHEN the request goes out, and the answer
    // is the menu of the WHOLE hub — the screen keeps only its own app's entries.
    loadMenu: vi.fn(async () => {
      const { moduleName, labels } = NAV[getLocale()] ?? NAV.es;
      const other = getLocale() === 'en' ? 'Customers' : 'Clientes';
      return [
        { moduleId: 'customers', moduleName: other, nav: { id: 'list', label: other, icon: 'people' } },
        { moduleId: 'tickets', moduleName, nav: { id: 'all', label: labels[0], icon: 'list' } },
        { moduleId: 'tickets', moduleName, nav: { id: 'sla', label: labels[1], icon: 'time' } },
      ];
    }),
    loadManifest: vi.fn(async () => ({})),
    loadComponent: vi.fn(async () => 'erp-tickets-all'),
  };
});
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
  default: {
    name: 'AppPage',
    props: ['title'],
    template: '<div><h1 data-testid="page-title">{{ title }}</h1><slot /><slot name="footer" /></div>',
  },
}));
vi.mock('../components/ModulePlanPanel.vue', () => ({
  default: { name: 'ModulePlanPanel', template: '<div />' },
}));
vi.mock('../components/ModuleSettingsForm.vue', () => ({
  default: { name: 'ModuleSettingsForm', template: '<div />' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ModuleView from './ModuleView.vue';
import { loadComponent, loadMenu } from '../lib/module-loader';
import { setLocale } from '../i18n';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const mounted: Array<{ unmount: () => void }> = [];

function mountModuleView() {
  const i18n = createI18n({
    legacy: false,
    locale: 'es',
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

type Hook = 'onIonViewWillEnter' | 'onIonViewWillLeave' | 'onIonViewDidLeave';

/** Calls the view's Ionic hooks exactly as `IonRouterOutlet`'s `fireLifecycle` does. */
function fire(wrapper: ReturnType<typeof mountModuleView>, hook: Hook): void {
  const proxy = (wrapper.vm as unknown as { $: { proxy: Record<string, unknown> } }).$.proxy;
  for (const h of (proxy[hook] as Array<() => void> | undefined) ?? []) h();
}

function tabLabels(wrapper: ReturnType<typeof mountModuleView>): string[] {
  // The button's accessible name is the same label the tab paints.
  return wrapper.findAll('ion-segment-button').map((b) => b.attributes('aria-label') ?? '');
}

beforeEach(() => {
  // The shell boots in its default language, before `/api/profile` has answered.
  setLocale('es');
  routeParams.moduleId = 'tickets';
  routeParams.navId = 'all';
  vi.mocked(loadMenu).mockClear();
  vi.mocked(loadComponent).mockClear();
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
  setLocale('es');
});

describe('the module tabbar follows the language applied after boot (hub#2353)', () => {
  it('repaints the tabs in English when the profile language lands after the module opened', async () => {
    const wrapper = mountModuleView();
    await settle();
    expect(tabLabels(wrapper)).toEqual(['Todos', 'Acuerdos']);

    setLocale('en'); // what `applyUserLocale` does once `/api/profile` answers
    await settle();

    expect(tabLabels(wrapper), 'the tabs kept the language of the first answer').toEqual(['All', 'Agreements']);
  });

  it('repaints the module heading too', async () => {
    const wrapper = mountModuleView();
    await settle();
    expect(wrapper.find('[data-testid="page-title"]').text()).toBe('Incidencias');

    setLocale('en');
    await settle();

    expect(wrapper.find('[data-testid="page-title"]').text()).toBe('Tickets');
  });

  it('goes back to Spanish when the language changes again', async () => {
    const wrapper = mountModuleView();
    await settle();
    setLocale('en');
    await settle();
    setLocale('es');
    await settle();

    expect(tabLabels(wrapper)).toEqual(['Todos', 'Acuerdos']);
  });

  it('does not remount the module screen: it repaints itself on the same event', async () => {
    const wrapper = mountModuleView();
    await settle();
    const screen = wrapper.find('erp-tickets-all').element;
    expect(loadComponent).toHaveBeenCalledTimes(1);

    setLocale('en');
    await settle();

    // A remount would throw away what the person had on screen (an open ticket, a half-typed form).
    expect(loadComponent).toHaveBeenCalledTimes(1);
    expect(wrapper.find('erp-tickets-all').element).toBe(screen);
    expect(tabLabels(wrapper)).toEqual(['All', 'Agreements']);
  });

  it('keeps the English labels when the change lands while the first answer is still on its way', async () => {
    // The first request goes out in Spanish and answers AFTER the change: its stale labels must
    // not be the last word.
    let releaseFirst: () => void = () => {};
    vi.mocked(loadMenu).mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => (releaseFirst = resolve));
      const { moduleName, labels } = NAV.es;
      return [
        { moduleId: 'tickets', moduleName, nav: { id: 'all', label: labels[0], icon: 'list' } },
        { moduleId: 'tickets', moduleName, nav: { id: 'sla', label: labels[1], icon: 'time' } },
      ] as never;
    });
    const wrapper = mountModuleView();
    await settle();

    setLocale('en');
    await settle();
    releaseFirst();
    await settle();

    expect(tabLabels(wrapper)).toEqual(['All', 'Agreements']);
    expect(wrapper.find('[data-testid="page-title"]').text()).toBe('Tickets');
  });

  it('ends in the LAST language when two changes cross on their way back', async () => {
    const wrapper = mountModuleView();
    await settle();
    // The English answer is slow; the Spanish one (asked after it) comes back first.
    let releaseEnglish: () => void = () => {};
    vi.mocked(loadMenu).mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => (releaseEnglish = resolve));
      const { moduleName, labels } = NAV.en;
      return [
        { moduleId: 'tickets', moduleName, nav: { id: 'all', label: labels[0], icon: 'list' } },
        { moduleId: 'tickets', moduleName, nav: { id: 'sla', label: labels[1], icon: 'time' } },
      ] as never;
    });

    setLocale('en');
    setLocale('es');
    await settle();
    releaseEnglish();
    await settle();

    expect(tabLabels(wrapper)).toEqual(['Todos', 'Acuerdos']);
    expect(wrapper.find('[data-testid="page-title"]').text()).toBe('Incidencias');
  });

  it('does not paint the tabs of the app it just left', async () => {
    const wrapper = mountModuleView();
    await settle();
    let releaseTickets: () => void = () => {};
    vi.mocked(loadMenu).mockImplementationOnce(async () => {
      await new Promise<void>((resolve) => (releaseTickets = resolve));
      const { moduleName, labels } = NAV.en;
      return [
        { moduleId: 'tickets', moduleName, nav: { id: 'all', label: labels[0], icon: 'list' } },
        { moduleId: 'tickets', moduleName, nav: { id: 'sla', label: labels[1], icon: 'time' } },
      ] as never;
    });
    vi.mocked(loadMenu).mockImplementationOnce(
      async () =>
        [
          { moduleId: 'customers', moduleName: 'Customers', nav: { id: 'list', label: 'List', icon: 'people' } },
          { moduleId: 'customers', moduleName: 'Customers', nav: { id: 'groups', label: 'Groups', icon: 'albums' } },
        ] as never,
    );

    setLocale('en'); // refresh for Tickets goes out…
    await settle();
    routeParams.moduleId = 'customers'; // …and the person opens Customers before it answers
    routeParams.navId = 'list';
    await settle();
    releaseTickets();
    await settle();

    expect(tabLabels(wrapper)).toEqual(['List', 'Groups']);
    expect(wrapper.find('[data-testid="page-title"]').text()).toBe('Customers');
  });

  it('keeps the tabs it has when the new answer fails or comes back without this app', async () => {
    const wrapper = mountModuleView();
    await settle();

    vi.mocked(loadMenu).mockRejectedValueOnce(new Error('offline'));
    setLocale('en');
    await settle();
    expect(tabLabels(wrapper)).toEqual(['Todos', 'Acuerdos']);

    vi.mocked(loadMenu).mockResolvedValueOnce([]);
    setLocale('es');
    await settle();
    expect(tabLabels(wrapper)).toEqual(['Todos', 'Acuerdos']);
    expect(wrapper.find('[data-testid="page-title"]').text()).toBe('Incidencias');
  });

  it('does not ask from a copy off screen: it remounts on the way back, in the new language', async () => {
    const wrapper = mountModuleView();
    await settle();
    fire(wrapper, 'onIonViewWillLeave');
    fire(wrapper, 'onIonViewDidLeave');
    const calls = vi.mocked(loadMenu).mock.calls.length;

    setLocale('en');
    await settle();
    expect(vi.mocked(loadMenu).mock.calls.length, 'a hidden copy fetched the navigation').toBe(calls);

    fire(wrapper, 'onIonViewWillEnter');
    await settle();
    expect(tabLabels(wrapper)).toEqual(['All', 'Agreements']);
  });

  it('stops listening once the screen is gone', async () => {
    const wrapper = mountModuleView();
    await settle();
    mounted.pop();
    wrapper.unmount();
    const calls = vi.mocked(loadMenu).mock.calls.length;

    setLocale('en');
    await settle();

    expect(vi.mocked(loadMenu).mock.calls.length).toBe(calls);
  });
});
