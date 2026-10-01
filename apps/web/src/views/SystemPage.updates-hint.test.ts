// @vitest-environment happy-dom
// hub#2332 — **System → Updates said nothing about the apps.**
//
// The owner who looks for «updates» in the obvious place found the hub's own history and a line
// saying the Hub updates itself, but not whether any of their apps had a new version, nor a way to
// go and update it. The tab now says it in one line, with the bell's own count (hub#1172: only what
// this hub can apply, only for whoever can update apps) and a way to «My apps»; «all up to date»
// when there is nothing, and «could not check» — never «up to date» — when the check failed.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import type { ModuleUpdateInfo } from '../lib/module-updates';

// A real ref: the template unwraps it, the notice reads `.value`.
const { admin, route } = await vi.hoisted(async () => {
  const vue = await import('vue');
  return { admin: vue.ref(true), route: vue.reactive({ path: '/system', hash: '#updates' }) };
});

const { push, replace, listModuleUpdates, systemInfo } = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  listModuleUpdates: vi.fn(),
  systemInfo: { value: { hubVersion: '1.4.0' } as { hubVersion: string } | null },
}));

vi.mock('../lib/session', async () => {
  const actual = await vi.importActual<typeof import('../lib/session')>('../lib/session');
  return {
    ...actual,
    isAdmin: admin,
    isAuthed: ref(true),
    user: ref({ id: 'owner' }),
  };
});
vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return { ...actual, listModuleUpdates, listInstalledModules: vi.fn(async () => []) };
});
vi.mock('../lib/update-history', async () => {
  const actual = await vi.importActual<typeof import('../lib/update-history')>('../lib/update-history');
  return { ...actual, fetchUpdateHistory: vi.fn(async () => []) };
});
vi.mock('../lib/bell-counters', () => ({ loadBellCounterModuleIds: vi.fn(async () => new Set()) }));
vi.mock('../lib/system', async () => {
  const actual = await vi.importActual<typeof import('../lib/system')>('../lib/system');
  return { ...actual, fetchSystemInfo: vi.fn(async () => systemInfo.value) };
});
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/toast', () => ({
  toast: vi.fn(),
  toastInfo: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/PlanLimitsPanel.vue', () => ({
  default: { name: 'PlanLimitsPanel', template: '<div />' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, push }),
}));

import SystemPage from './SystemPage.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';
import {
  markModuleUpdatesUnknown,
  publishModuleUpdates,
  retryModuleUpdateNotice,
  stopModuleUpdateNoticeWatch,
} from '../lib/module-update-notice';

const BLOCK = '[data-testid="system-app-updates"]';
const GO = '[data-testid="system-app-updates-go"]';
const RETRY = '[data-testid="system-app-updates-retry"]';

function app(id: string, extra: Partial<ModuleUpdateInfo> = {}): ModuleUpdateInfo {
  return {
    module_id: id,
    installed: '1.0.0',
    latest: '1.1.0',
    update_available: true,
    pinned: null,
    checked: true,
    ...extra,
  };
}

function upToDate(id: string): ModuleUpdateInfo {
  return app(id, { latest: '1.0.0', update_available: false });
}

async function mountSystem(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en, es },
  });
  const wrapper = mount(SystemPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
  await flushPromises();
  return wrapper;
}

function plural(message: string, n: number): string {
  const [one, many] = message.split(' | ');
  return (n === 1 ? one : many).replace('{n}', String(n));
}

beforeEach(() => {
  admin.value = true;
  push.mockReset();
  replace.mockReset();
  route.path = '/system';
  route.hash = '#updates';
  listModuleUpdates.mockReset();
  systemInfo.value = { hubVersion: '1.4.0' };
  stopModuleUpdateNoticeWatch();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('System → Updates says whether the apps have a new version', () => {
  it('the_updates_tab_links_to_apps_when_modules_are_behind_hub1172', async () => {
    publishModuleUpdates([app('sales'), app('customers'), upToDate('inventory')], '1.4.0');
    const wrapper = await mountSystem();

    const block = wrapper.find(BLOCK);
    expect(block.exists()).toBe(true);
    expect(block.text()).toContain(plural(en.system.appUpdates.available, 2));
    expect(block.text()).toContain(en.system.appUpdates.goToMyApps);
    expect(block.attributes('tone')).toBe('info');

    await wrapper.find(GO).trigger('click');
    expect(push).toHaveBeenCalledWith('/apps#mine');
  });

  it('says it of a single app in the singular', async () => {
    publishModuleUpdates([app('sales'), upToDate('inventory')], '1.4.0');
    const wrapper = await mountSystem();
    expect(wrapper.find(BLOCK).text()).toContain(plural(en.system.appUpdates.available, 1));
  });

  it('says the apps are all up to date when none is behind, with nothing to go to', async () => {
    publishModuleUpdates([upToDate('sales'), upToDate('inventory')], '1.4.0');
    const wrapper = await mountSystem();
    const block = wrapper.find(BLOCK);
    expect(block.text()).toContain(en.system.appUpdates.allUpToDate);
    expect(block.attributes('tone')).toBe('success');
    expect(wrapper.find(GO).exists()).toBe(false);
    expect(wrapper.find(RETRY).exists()).toBe(false);
  });

  it('does not count an update that needs a newer ERPlora: the owner could never apply it', async () => {
    publishModuleUpdates([app('sales', { latest_min_erplora_version: '9.0.0' })], '1.4.0');
    const wrapper = await mountSystem();
    expect(wrapper.find(BLOCK).text()).toContain(en.system.appUpdates.allUpToDate);
    expect(wrapper.find(GO).exists()).toBe(false);
  });

  it('says it could not check — not «up to date» — and offers to check again', async () => {
    markModuleUpdatesUnknown();
    let answer!: (u: ModuleUpdateInfo[]) => void;
    listModuleUpdates.mockReturnValue(new Promise<ModuleUpdateInfo[]>((r) => (answer = r)));
    const wrapper = await mountSystem();

    const block = wrapper.find(BLOCK);
    expect(block.text()).toContain(en.topbar.moduleUpdatesUnknownBody);
    expect(block.text()).not.toContain(en.system.appUpdates.allUpToDate);
    // A failed check is a warning, never the green tick of «all up to date».
    expect(block.attributes('tone')).toBe('warning');
    expect(block.attributes('icon')).not.toBe('checkmark-circle-outline');

    await wrapper.find(RETRY).trigger('click');
    await flushPromises();
    expect(listModuleUpdates).toHaveBeenCalledTimes(1);
    expect(wrapper.find(RETRY).text()).toContain(en.topbar.moduleUpdatesChecking);
    expect((wrapper.find(RETRY).element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);

    answer([app('sales')]);
    await flushPromises();
    expect(wrapper.find(BLOCK).text()).toContain(plural(en.system.appUpdates.available, 1));
    expect(wrapper.find(RETRY).exists()).toBe(false);
  });

  it('keeps the known updates and the way to them when a later check fails', async () => {
    publishModuleUpdates([app('sales'), app('customers')], '1.4.0');
    markModuleUpdatesUnknown();
    const wrapper = await mountSystem();
    expect(wrapper.find(BLOCK).text()).toContain(plural(en.system.appUpdates.available, 2));
    expect(wrapper.find(GO).exists()).toBe(true);
    // The count wins: one way out, not «Go to My apps» and «Check again» side by side.
    expect(wrapper.find(RETRY).exists()).toBe(false);
  });

  it('says it is checking while the first check is out, not «up to date»', async () => {
    let answer!: (u: ModuleUpdateInfo[]) => void;
    listModuleUpdates.mockReturnValue(new Promise<ModuleUpdateInfo[]>((r) => (answer = r)));
    retryModuleUpdateNotice();
    const wrapper = await mountSystem();
    const block = wrapper.find(BLOCK);
    expect(block.text()).toContain(en.system.appUpdates.checking);
    expect(block.text()).not.toContain(en.system.appUpdates.allUpToDate);
    expect(block.attributes('tone')).toBe('neutral');
    expect(block.attributes('icon')).not.toBe('checkmark-circle-outline');

    answer([upToDate('sales')]);
    await flushPromises();
    expect(wrapper.find(BLOCK).text()).toContain(en.system.appUpdates.allUpToDate);
  });

  it('is not shown to someone who cannot update apps', async () => {
    admin.value = false;
    const wrapper = await mountSystem();
    expect(wrapper.find(BLOCK).exists()).toBe(false);
  });

  it('says it in Spanish too', async () => {
    publishModuleUpdates([app('sales'), app('customers')], '1.4.0');
    const wrapper = await mountSystem('es');
    const block = wrapper.find(BLOCK);
    expect(block.text()).toContain(plural(es.system.appUpdates.available, 2));
    expect(block.text()).toContain(es.system.appUpdates.goToMyApps);
  });
});

// Ionic keeps System mounted after «Go to My apps», and `useRoute()` is the app's one route: the
// tab ↔ hash sync used to read `#mine` as an unknown System tab and write `#resources` onto the
// Apps URL (`/apps#mine` → `/apps#resources`).
describe('leaving System for «My apps»', () => {
  it("leaves the next screen's address alone", async () => {
    publishModuleUpdates([app('sales')], '1.4.0');
    const wrapper = await mountSystem();
    await wrapper.find(GO).trigger('click');
    route.path = '/apps';
    route.hash = '#mine';
    await flushPromises();
    expect(replace).not.toHaveBeenCalled();
    expect(wrapper.find(BLOCK).exists()).toBe(true);
  });

  // The guard above must not turn into «remember the last tab»: back on a plain /system the address
  // says Resources, as it did before the guard (develop re-read the hash on the way out).
  it('coming back to a plain /system opens the tab its address names', async () => {
    const wrapper = await mountSystem();
    expect(wrapper.find(BLOCK).exists()).toBe(true);
    route.path = '/home';
    route.hash = '';
    await flushPromises();
    route.path = '/system';
    await flushPromises();
    expect(wrapper.find(BLOCK).exists()).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });

  it('still follows its own address: a link to another System tab opens it', async () => {
    const wrapper = await mountSystem();
    route.hash = '#logs';
    await flushPromises();
    expect(wrapper.find(BLOCK).exists()).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });
});
