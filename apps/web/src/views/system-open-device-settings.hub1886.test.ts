// @vitest-environment happy-dom
// hub#1886 — **a button that TAKES you to the device settings, instead of a sentence about them.**
//
// Refused twice, Android stops showing a permission dialog for the life of the install. From then
// on the only way back is ERPlora's page in the device settings — and all the app did was DESCRIBE
// it («Open its settings, find ERPlora and…»), leaving the owner to hunt for a system screen that
// every brand organises differently. Every app that meets this offers a button that goes there.
//
// Pinned here:
//
//  1. both blocked cards (notices, printer search) carry the button, and it opens the page through
//     the plugin — the same door for both, because it is the same page;
//  2. where there is no such page (desktop, browser, an Android without the permission) there is
//     no button, because there is no card;
//  3. an installed app older than the command (the web ships with the hub, the APK with the store)
//     answers «command not found»: the tap then falls back to saying where to go, never silence;
//  4. the label is translated.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { permissionStatus, invokeSpy } = vi.hoisted(() => ({
  /** What `check_permissions` answers. */
  permissionStatus: { value: null as Record<string, boolean> | null },
  invokeSpy: vi.fn<(cmd: string, args?: Record<string, unknown>) => Promise<unknown>>(),
}));

vi.mock('../lib/device', async () => {
  const actual = await vi.importActual<typeof import('../lib/device')>('../lib/device');
  return { ...actual, isTauri: () => true, invokeTauri: invokeSpy };
});

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  // hub#2046: the notices card exists only on a hub the shell sends notices for (today, one with a
  // kitchen), so the hub under test has one — otherwise the button this file pins is never there.
  return {
    ...actual,
    listInstalledModules: vi.fn(async () => [
      { id: 'printing', status: 'active' },
      { id: 'kitchen', status: 'active' },
    ]),
  };
});

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
import { toast } from '../lib/toast';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const NOTIFICATIONS = 'android.permission.POST_NOTIFICATIONS';
const LOCAL_NETWORK = 'android.permission.ACCESS_LOCAL_NETWORK';
const OPEN_APP_SETTINGS = 'plugin:erplora-android|open_app_settings';

const NOTICES_BUTTON = '[data-testid="system-notices-open-settings"]';
const LOCAL_NETWORK_BUTTON = '[data-testid="system-local-network-open-settings"]';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

async function mountSystem() {
  const wrapper = mount(SystemPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
  await flushPromises();
  return wrapper;
}

function settingsOpenings(): number {
  return invokeSpy.mock.calls.filter(([cmd]) => cmd === OPEN_APP_SETTINGS).length;
}

beforeEach(() => {
  vi.mocked(toast).mockClear();
  permissionStatus.value = null;
  invokeSpy.mockReset();
  invokeSpy.mockImplementation(async (cmd: string) => {
    if (cmd === 'plugin:erplora-android|check_permissions') return permissionStatus.value;
    // Kotlin's `invoke.resolve()` with no data reaches the web as `null` (hub#2024).
    if (cmd === OPEN_APP_SETTINGS) return null;
    return { version: '1.4.0' };
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('with a permission Android no longer asks for', () => {
  beforeEach(() => {
    permissionStatus.value = { [NOTIFICATIONS]: false, [LOCAL_NETWORK]: false };
  });

  it('the notices card takes the owner to the device settings', async () => {
    const wrapper = await mountSystem();
    const button = wrapper.get(NOTICES_BUTTON);
    expect(button.text()).toContain(en.system.openDeviceSettings);

    await button.trigger('click');
    await flushPromises();

    expect(settingsOpenings()).toBe(1);
    // Opened: the settings page is on screen and says it all. Nothing to toast on top.
    expect(toast).not.toHaveBeenCalled();
  });

  it('the printer-search card takes the owner to the same page', async () => {
    const wrapper = await mountSystem();
    const button = wrapper.get(LOCAL_NETWORK_BUTTON);
    expect(button.text()).toContain(en.system.openDeviceSettings);

    await button.trigger('click');
    await flushPromises();

    expect(settingsOpenings()).toBe(1);
    expect(toast).not.toHaveBeenCalled();
  });

  it('on an installed app older than the button, says where to go instead of doing nothing', async () => {
    // The web ships with the hub and the APK with the store: a till can run this screen on an app
    // that has no such command yet, and Tauri answers «command not found».
    invokeSpy.mockImplementation(async (cmd: string) => {
      if (cmd === 'plugin:erplora-android|check_permissions') return permissionStatus.value;
      if (cmd === OPEN_APP_SETTINGS) throw new Error('command open_app_settings not found');
      return { version: '1.4.0' };
    });
    const wrapper = await mountSystem();

    await wrapper.get(NOTICES_BUTTON).trigger('click');
    await flushPromises();
    expect(vi.mocked(toast).mock.calls[0]?.[0]).toBe(en.system.notices.blockedInSettings);

    await wrapper.get(LOCAL_NETWORK_BUTTON).trigger('click');
    await flushPromises();
    expect(vi.mocked(toast).mock.calls[1]?.[0]).toBe(en.hardware.localNetwork.blockedInSettings);
  });

  it('has the button translated into Spanish (ADR-0055/0199)', async () => {
    expect(es.system.openDeviceSettings).toBe('Abrir los ajustes');
    i18n.global.locale.value = 'es';
    try {
      const wrapper = await mountSystem();
      expect(wrapper.get(NOTICES_BUTTON).text()).toContain(es.system.openDeviceSettings);
      expect(wrapper.get(LOCAL_NETWORK_BUTTON).text()).toContain(es.system.openDeviceSettings);
    } finally {
      i18n.global.locale.value = 'en';
    }
  });
});

describe('where there is no such page, there is no button', () => {
  it('stays out with both permissions granted', async () => {
    permissionStatus.value = { [NOTIFICATIONS]: true, [LOCAL_NETWORK]: true };
    const wrapper = await mountSystem();

    expect(wrapper.find(NOTICES_BUTTON).exists()).toBe(false);
    expect(wrapper.find(LOCAL_NETWORK_BUTTON).exists()).toBe(false);
  });

  it('stays out on desktop and in a browser, where the plugin reports nothing', async () => {
    for (const status of [{}, null]) {
      permissionStatus.value = status;
      const wrapper = await mountSystem();
      expect(wrapper.find(NOTICES_BUTTON).exists()).toBe(false);
      expect(wrapper.find(LOCAL_NETWORK_BUTTON).exists()).toBe(false);
    }
  });
});
