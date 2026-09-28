// @vitest-environment happy-dom
// hub#1773 — **the other half: a «no» that the screen says out loud, and a way back.**
//
// Asking in context is only half the fix. Android is nearly one-way about `ACCESS_LOCAL_NETWORK`:
// once refused, the system stops presenting its dialog, and from then on every search comes back
// empty however many printers are switched on. The Printing screen does say WHY when the search is
// blocked (hub#338 made a blocked scan a typed refusal instead of an empty list) — but saying it is
// not the same as offering the way back, and the owner who already dismissed that sentence has
// nowhere left to go.
//
// So System › your printer says it, in the same place and the same shape as the notices row right
// above it (hub#1732), and offers the ask again.
//
// The four things pinned here are the four ways a "state row" goes wrong:
//
//  1. it appears when the state is real — and ONLY then;
//  2. it does not appear on a platform that has no such permission (the desktop app, a browser,
//     every Android below 17), where claiming the search is blocked would be a false alarm;
//  3. the button leads somewhere: granted, it says so and the row goes; refused again, it names
//     the device settings, because that is the only door left;
//  4. it never speaks about a permission — it speaks about the printer.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { permissionStatus, ensureLanSpy } = vi.hoisted(() => ({
  /** What `check_permissions` answers. The whole suite turns on this map. */
  permissionStatus: { value: null as Record<string, boolean> | null },
  ensureLanSpy: vi.fn<(deps: { force?: boolean }) => Promise<string>>(async () => 'granted'),
}));

// SystemPage reads the modules with a bell counter (hub#2306) through `module-loader`, whose icon
// chain (`~icons/…?raw`) the vitest transform denies — stubbed like DataPanel/dashboard-widgets.
vi.mock('../lib/module-loader', () => ({ loadInstalledManifests: vi.fn(async () => []) }));
vi.mock('../lib/device', async () => {
  const actual = await vi.importActual<typeof import('../lib/device')>('../lib/device');
  return {
    ...actual,
    isTauri: () => true,
    invokeTauri: vi.fn(async (cmd: string) =>
      cmd === 'plugin:erplora-android|check_permissions'
        ? permissionStatus.value
        : { version: '1.4.0' },
    ),
  };
});

vi.mock('../lib/local-network-permission', async () => {
  const actual =
    await vi.importActual<typeof import('../lib/local-network-permission')>(
      '../lib/local-network-permission',
    );
  return { ...actual, ensureLocalNetworkPermission: ensureLanSpy };
});

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return { ...actual, listInstalledModules: vi.fn(async () => [{ id: 'printing', status: 'active' }]) };
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

const LOCAL_NETWORK = 'android.permission.ACCESS_LOCAL_NETWORK';
const NOTIFICATIONS = 'android.permission.POST_NOTIFICATIONS';

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

beforeEach(() => {
  ensureLanSpy.mockClear();
  ensureLanSpy.mockResolvedValue('granted');
  vi.mocked(toast).mockClear();
  permissionStatus.value = null;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('when this device is not allowed to look for a printer', () => {
  beforeEach(() => {
    // Denied, and the notices granted: the two rows are independent, and only one belongs here.
    permissionStatus.value = { [LOCAL_NETWORK]: false, [NOTIFICATIONS]: true };
  });

  it('says so, in words about the printer and never about a permission', async () => {
    const wrapper = await mountSystem();

    expect(wrapper.text()).toContain(en.hardware.localNetwork.blockedTitle);
    expect(wrapper.text()).toContain(en.hardware.localNetwork.blockedDetail);
    // The vocabulary rule of ADR-0254: nobody who runs a bar knows what ACCESS_LOCAL_NETWORK is.
    expect(wrapper.text()).not.toContain('ACCESS_LOCAL_NETWORK');
    expect(wrapper.text()).not.toContain('permission');
  });

  it('offers the ask again, and FORCES it — the scan never asks twice on its own', async () => {
    const wrapper = await mountSystem();
    await wrapper.get('[data-testid="system-local-network-allow"]').trigger('click');
    await flushPromises();

    expect(ensureLanSpy).toHaveBeenCalledTimes(1);
    expect(ensureLanSpy.mock.calls[0]?.[0]?.force).toBe(true);
  });

  it('confirms it when the search is allowed, and stops warning about it', async () => {
    const wrapper = await mountSystem();
    // The permission is granted while the dialog is up: the screen re-reads the real state
    // instead of trusting what it asked for.
    ensureLanSpy.mockImplementation(async () => {
      permissionStatus.value = { [LOCAL_NETWORK]: true, [NOTIFICATIONS]: true };
      return 'granted';
    });
    await wrapper.get('[data-testid="system-local-network-allow"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(toast).mock.calls[0]?.[0]).toBe(en.hardware.localNetwork.turnedOn);
    expect(wrapper.text()).not.toContain(en.hardware.localNetwork.blockedTitle);
  });

  it('reads the system back, not its own request: granted in the device settings counts', async () => {
    // A real sequence, and the reason the state is re-read instead of taken from the ask: the
    // user goes to the device settings, allows the local network there, comes back and taps «Not
    // now» on our sheet. The ask reports the state it saw before all that; the system does not.
    ensureLanSpy.mockImplementation(async () => {
      permissionStatus.value = { [LOCAL_NETWORK]: true, [NOTIFICATIONS]: true };
      return 'denied';
    });
    const wrapper = await mountSystem();
    await wrapper.get('[data-testid="system-local-network-allow"]').trigger('click');
    await flushPromises();

    expect(wrapper.text()).not.toContain(en.hardware.localNetwork.blockedTitle);
    expect(vi.mocked(toast).mock.calls[0]?.[0]).toBe(en.hardware.localNetwork.turnedOn);
  });

  it('names the device settings when the system will not ask again', async () => {
    // Two refusals and Android stops showing its dialog for good. Leaving the button silent here
    // is the dead end the issue describes: the user taps, nothing happens, nothing is explained.
    ensureLanSpy.mockResolvedValue('denied');
    const wrapper = await mountSystem();
    await wrapper.get('[data-testid="system-local-network-allow"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(toast).mock.calls[0]?.[0]).toBe(en.hardware.localNetwork.blockedInSettings);
    expect(wrapper.text()).toContain(en.hardware.localNetwork.blockedTitle);
  });

  it('has the whole row translated into Spanish (ADR-0055/0199)', async () => {
    i18n.global.locale.value = 'es';
    try {
      const wrapper = await mountSystem();
      expect(wrapper.text()).toContain(es.hardware.localNetwork.blockedTitle);
      expect(wrapper.text()).toContain(es.hardware.localNetwork.blockedAction);
    } finally {
      i18n.global.locale.value = 'en';
    }
  });

  it('re-reads the state when the app comes back to the foreground', async () => {
    // The toast sends the user to the device settings, and coming back from them is not a
    // navigation: no mount, no ion-view hook fires. Without this the row keeps saying «blocked»
    // about a device that has just been fixed.
    const wrapper = await mountSystem();
    expect(wrapper.text()).toContain(en.hardware.localNetwork.blockedTitle);

    permissionStatus.value = { [LOCAL_NETWORK]: true, [NOTIFICATIONS]: true };
    document.dispatchEvent(new Event('visibilitychange'));
    await flushPromises();

    expect(wrapper.text()).not.toContain(en.hardware.localNetwork.blockedTitle);
  });
});

describe('and when it can look, the row is simply not there', () => {
  it('stays quiet with the local network granted', async () => {
    permissionStatus.value = { [LOCAL_NETWORK]: true };
    const wrapper = await mountSystem();

    expect(wrapper.text()).not.toContain(en.hardware.localNetwork.blockedTitle);
  });

  it('stays quiet where the permission does not exist (desktop app, browser, old Android)', async () => {
    // An empty map is the desktop shell. Claiming the printer search is blocked on a Mac that
    // finds printers fine is a false alarm about something that works.
    permissionStatus.value = {};
    const wrapper = await mountSystem();

    expect(wrapper.text()).not.toContain(en.hardware.localNetwork.blockedTitle);
  });

  it('stays quiet when the plugin cannot answer at all', async () => {
    permissionStatus.value = null;
    const wrapper = await mountSystem();

    expect(wrapper.text()).not.toContain(en.hardware.localNetwork.blockedTitle);
  });
});
