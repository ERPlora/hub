// @vitest-environment happy-dom
// hub#1732 — **the other half: a «no» that the screen says out loud.**
//
// Asking in context is only half the fix. Android is nearly one-way about this permission: once
// refused, the system stops presenting its dialog, and from then on the till cannot show a single
// notice for the life of the install — with nothing anywhere saying so. The symptom is a kitchen
// that stops hearing about orders and an owner with no reason to suspect a permission.
//
// So System › this device says it, in the same place and the same shape as the printer card right
// above it, and offers the ask again. The comparison the issue itself draws is the local-network
// permission on the Printing screen, which does exactly this and does it well.
//
// The three things pinned here are the three ways a "state row" goes wrong:
//
//  1. it appears when the state is real — and ONLY then;
//  2. it does not appear on a platform that has no such permission (the desktop app, a browser,
//     every Android below 13), where claiming the notices are off would be a false alarm;
//  3. the button leads somewhere: granted, it says so and the row goes; refused again, it names
//     the device settings, because that is the only door left.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { permissionStatus, ensureSpy } = vi.hoisted(() => ({
  /** What `check_permissions` answers. The whole suite turns on this map. */
  permissionStatus: { value: null as Record<string, boolean> | null },
  ensureSpy: vi.fn<(deps: { force?: boolean }) => Promise<string>>(async () => 'granted'),
}));

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

vi.mock('../lib/notification-permission', async () => {
  const actual =
    await vi.importActual<typeof import('../lib/notification-permission')>(
      '../lib/notification-permission',
    );
  return { ...actual, ensureNotificationPermission: ensureSpy };
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
  ensureSpy.mockClear();
  ensureSpy.mockResolvedValue('granted');
  vi.mocked(toast).mockClear();
  permissionStatus.value = null;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('when this device cannot warn anybody', () => {
  beforeEach(() => {
    permissionStatus.value = { [NOTIFICATIONS]: false };
  });

  it('says so, in words about orders and never about a permission', async () => {
    const wrapper = await mountSystem();

    expect(wrapper.text()).toContain(en.system.notices.blockedTitle);
    expect(wrapper.text()).toContain(en.system.notices.blockedDetail);
    // The vocabulary rule of ADR-0254: nobody who runs a bar knows what POST_NOTIFICATIONS is.
    expect(wrapper.text()).not.toContain('POST_NOTIFICATIONS');
    expect(wrapper.text()).not.toContain('permission');
  });

  it('offers the ask again, and FORCES it — the boot never asks twice on its own', async () => {
    const wrapper = await mountSystem();
    await wrapper.get('[data-test="notices-turn-on"]').trigger('click');
    await flushPromises();

    expect(ensureSpy).toHaveBeenCalledTimes(1);
    expect(ensureSpy.mock.calls[0]?.[0]?.force).toBe(true);
  });

  it('confirms it when the notices come on, and stops warning about them', async () => {
    const wrapper = await mountSystem();
    // The permission is granted while the dialog is up: the screen re-reads the real state
    // instead of trusting what it asked for.
    ensureSpy.mockImplementation(async () => {
      permissionStatus.value = { [NOTIFICATIONS]: true };
      return 'granted';
    });
    await wrapper.get('[data-test="notices-turn-on"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(toast).mock.calls[0]?.[0]).toBe(en.system.notices.turnedOn);
    expect(wrapper.text()).not.toContain(en.system.notices.blockedTitle);
  });

  it('reads the system back, not its own request: granted in the device settings counts', async () => {
    // A real sequence, and the reason the state is re-read instead of taken from the ask: the
    // user goes to the device settings, turns the notices on there, comes back and taps «Not
    // now» on our sheet. The ask reports the state it saw before all that; the system does not.
    ensureSpy.mockImplementation(async () => {
      permissionStatus.value = { [NOTIFICATIONS]: true };
      return 'denied';
    });
    const wrapper = await mountSystem();
    await wrapper.get('[data-test="notices-turn-on"]').trigger('click');
    await flushPromises();

    expect(wrapper.text()).not.toContain(en.system.notices.blockedTitle);
    expect(vi.mocked(toast).mock.calls[0]?.[0]).toBe(en.system.notices.turnedOn);
  });

  it('names the device settings when the system will not ask again', async () => {
    // Two refusals and Android stops showing its dialog for good. Leaving the button silent here
    // is the dead end the issue describes: the user taps, nothing happens, nothing is explained.
    ensureSpy.mockResolvedValue('denied');
    const wrapper = await mountSystem();
    await wrapper.get('[data-test="notices-turn-on"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(toast).mock.calls[0]?.[0]).toBe(en.system.notices.blockedInSettings);
    expect(wrapper.text()).toContain(en.system.notices.blockedTitle);
  });

  it('has the whole row translated into Spanish (ADR-0055/0199)', async () => {
    i18n.global.locale.value = 'es';
    try {
      const wrapper = await mountSystem();
      expect(wrapper.text()).toContain(es.system.notices.blockedTitle);
      expect(wrapper.text()).toContain(es.system.notices.blockedAction);
    } finally {
      i18n.global.locale.value = 'en';
    }
  });
});

describe('and when it can, the row is simply not there', () => {
  it('stays quiet with the notices granted', async () => {
    permissionStatus.value = { [NOTIFICATIONS]: true };
    const wrapper = await mountSystem();

    expect(wrapper.text()).not.toContain(en.system.notices.blockedTitle);
  });

  it('stays quiet where the permission does not exist — desktop, browser, Android 12 and below', async () => {
    // `PermissionPolicy.statusOf` reports only what THIS Android knows, and on desktop the map is
    // empty. Reading an absent key as «off» would put a false alarm on a Mac that notifies fine.
    permissionStatus.value = { 'android.permission.ACCESS_LOCAL_NETWORK': false };
    expect((await mountSystem()).text()).not.toContain(en.system.notices.blockedTitle);

    permissionStatus.value = {};
    expect((await mountSystem()).text()).not.toContain(en.system.notices.blockedTitle);

    permissionStatus.value = null;
    expect((await mountSystem()).text()).not.toContain(en.system.notices.blockedTitle);
  });
});
