// @vitest-environment happy-dom
// hub#2306 — **System never told a WhatsApp-only business that its notices were off.**
//
// The «Notices are off» card only appears on a hub that has something to warn about (hub#2046),
// and that «something» was a fixed list: the kitchen and appointments. Since hub#2303 a module's
// bell counter sends notices too, so a hub whose only notice source is the WhatsApp inbox has to
// see the card like a restaurant does — while a bell module that is installed but switched off,
// or a hub with nothing on the bell, stays quiet.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { permissionStatus, installedModules, bellModules } = vi.hoisted(() => ({
  permissionStatus: { value: null as Record<string, boolean> | null },
  installedModules: { value: [] as { id: string; status: string }[] },
  bellModules: { value: new Set<string>() as ReadonlySet<string> },
}));

vi.mock('../lib/device', async () => {
  const actual = await vi.importActual<typeof import('../lib/device')>('../lib/device');
  return {
    ...actual,
    isTauri: () => true,
    invokeTauri: vi.fn(async (cmd: string) =>
      cmd === 'plugin:erplora-android|check_permissions' ? permissionStatus.value : { version: '1.4.0' },
    ),
  };
});

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return { ...actual, listInstalledModules: vi.fn(async () => installedModules.value) };
});

// Which modules put a counter on the bell is read with the bell's own rule (its own test); here it
// is the input. `module-loader` is not imported at all: its icon chain is denied by vitest.
vi.mock('../lib/bell-counters', () => ({ loadBellCounterModuleIds: vi.fn(async () => bellModules.value) }));

vi.mock('../lib/system', () => ({ fetchSystemInfo: vi.fn(async () => null) }));
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
  useRoute: () => ({ hash: '' }),
  useRouter: () => ({ replace: vi.fn() }),
}));

import SystemPage from './SystemPage.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const NOTIFICATIONS = 'android.permission.POST_NOTIFICATIONS';

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

beforeEach(() => {
  // The notices refused on an Android 13+ inside the app: the only state where the card can exist.
  permissionStatus.value = { [NOTIFICATIONS]: false };
  installedModules.value = [
    { id: 'whatsapp_inbox', status: 'active' },
    { id: 'customers', status: 'active' },
  ];
  bellModules.value = new Set(['whatsapp_inbox']);
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('the «notices are off» card on a WhatsApp-only hub', () => {
  it('appears, because the inbox puts a counter on the bell', async () => {
    const wrapper = await mountSystem();
    expect(wrapper.text()).toContain(en.system.notices.blockedTitle);
    expect(wrapper.find('[data-testid="system-notices-turn-on"]').exists()).toBe(true);
  });

  it('says it in Spanish too', async () => {
    const wrapper = await mountSystem('es');
    expect(wrapper.text()).toContain(es.system.notices.blockedTitle);
  });

  it('stays away when the bell module is installed but switched off', async () => {
    installedModules.value = [
      { id: 'whatsapp_inbox', status: 'inactive' },
      { id: 'customers', status: 'active' },
    ];
    const wrapper = await mountSystem();
    expect(wrapper.find('[data-testid="system-notices-turn-on"]').exists()).toBe(false);
  });

  it('stays away when nothing active puts a counter on the bell', async () => {
    bellModules.value = new Set();
    const wrapper = await mountSystem();
    expect(wrapper.find('[data-testid="system-notices-turn-on"]').exists()).toBe(false);
  });
});
