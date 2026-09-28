// @vitest-environment happy-dom
// hub#456 (2/2) — **the shell's door to the hand-over**.
//
// The overlay and the swap are pinned elsewhere (`UserSwitchOverlay.test.ts`, `lib/user-switch`).
// What this suite pins is the wiring, which is where the feature is won or lost:
//
//   - the entry lives in the USER MENU, next to «Sign out» and instead of it — the two are the same
//     decision («somebody else takes this till»), and the sector's standard (Square, Toast;
//     decision #658) is that the cheap one is right there beside the expensive one;
//   - pressing it opens an overlay OVER the shell. It does not navigate and it does not sign out:
//     navigating is exactly what loses the sale, and it is the whole reason hub#456 stayed open
//     after its first half (idle sign-out, hub#628) shipped;
//   - a `personal` device is not offered it at all;
//   - and the shell ASKS the hub what kind of device this is once inside. Only the login screen
//     ever asked (`loadDeviceMode`), so on a reloaded session the answer defaults to «not enrolled»
//     — the entry would never appear on the one device it is for.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { route, replace } = vi.hoisted(() => ({
  route: { path: '/dashboard', name: 'dashboard' as string, meta: { auth: true } as Record<string, unknown> },
  replace: vi.fn(),
}));

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue');
  const shared = reactive(route);
  return { useRoute: () => shared, useRouter: () => ({ push: vi.fn(), replace }) };
});

// The hub's answer about this device is the double; the RULE that reads it (`offersUserSwitch`,
// through `lib/user-switch`) is the real one — that is what is under test.
const loadDeviceMode = vi.fn(async () => 'shared' as const);
vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  return {
    deviceMode: ref<'shared' | 'personal'>('shared'),
    deviceTrusted: ref(false),
    deviceModeReady: ref(true),
    loadDeviceMode: () => loadDeviceMode(),
  };
});

// Everything else the shell wakes up on mount is scenery: this suite is about the hand-over door.
vi.mock('../lib/nav', () => ({ refreshModuleNav: vi.fn(async () => {}) }));
vi.mock('../lib/entitlement', async () => {
  const { ref } = await import('vue');
  return { resolveEntitlement: vi.fn(async () => {}), needsActivation: ref(false) };
});
vi.mock('../lib/device', () => ({ getDeviceContext: vi.fn(async () => null) }));
vi.mock('../lib/hub-settings', () => ({ getHubSettings: vi.fn(async () => ({ language: 'en' })) }));
vi.mock('../lib/user-profile', () => ({
  getUserProfile: vi.fn(async () => null),
  resetUserProfile: vi.fn(),
}));
vi.mock('../lib/setup-status', () => ({
  refreshSetupStatus: vi.fn(async () => {}),
  refreshSetupStatusOnLocaleChange: vi.fn(() => () => {}),
}));
vi.mock('../lib/app-update', () => ({ bootAppUpdateWatch: vi.fn() }));
vi.mock('../lib/dead-letter', () => ({ bootDeadLetterWatch: vi.fn() }));
// Its chain reaches `lib/icons` (virtual `~icons/…?raw` ids this environment denies); the bell has its
// own tests (`lib/bell-counters.test.ts`).
vi.mock('../lib/bell-counters', () => ({ bootBellCountersWatch: vi.fn() }));
vi.mock('../lib/idle-logout', () => ({ installIdleLogout: vi.fn() }));
vi.mock('../lib/toast', () => ({ toast: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/upgrade-plan-link', () => ({
  planUpgradeIsOfferable: () => true,
  upgradePlanUrl: () => 'https://erplora.com/plan',
}));
vi.mock('../lib/shell-menu', () => ({
  SHELL_MENU_ID: 'shell-menu',
  runAfterShellMenuCloses: vi.fn(async (fn: () => unknown) => fn()),
}));
vi.mock('../lib/api-docs', async () => {
  const { ref } = await import('vue');
  return { apiDocsEnabled: ref(false) };
});
vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return {
    getClient: () => ({ on: () => () => {} }),
    pinUsers: ref<Array<{ id: string; name: string; role: string }>>([]),
  };
});
vi.mock('../i18n', () => ({ bootHubLanguage: vi.fn(), resetUserLocale: vi.fn() }));
vi.mock('./AssistantDrawer.vue', () => ({ default: { name: 'AssistantDrawer', template: '<div />' } }));
vi.mock('./ElevationDialog.vue', () => ({ default: { name: 'ElevationDialog', template: '<div />' } }));
vi.mock('./SidebarAppUpdate.vue', () => ({ default: { name: 'SidebarAppUpdate', template: '<div />' } }));
vi.mock('./HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span :data-icon="name" />' },
}));

import App from '../App.vue';
import { setHubSession, setUser } from '../lib/session';
import { deviceMode, deviceTrusted } from '../lib/device-mode';
import { pinPolicy } from '../lib/pin-policy';
import { closeUserSwitch, userSwitchOpen } from '../lib/user-switch';
import en from '../i18n/locales/en';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
});

async function mountShell() {
  const wrapper = mount(App, {
    shallow: true,
    global: {
      plugins: [i18n],
      renderStubDefaultSlot: true,
      stubs: { AuthenticatedChrome: false },
    },
  });
  await flushPromises();
  return wrapper;
}

/** A cashier signed in at the counter till the hub vouched for. */
function seedCounterTill(): void {
  setUser({ id: 'u-nacho', name: 'Nacho', email: 'nacho@erplora.test', role: 'employee', permissions: [] });
  setHubSession('sess-nacho');
  deviceMode.value = 'shared';
  deviceTrusted.value = true;
  pinPolicy.value = 'per_shift';
}

beforeEach(() => {
  setUser(null);
  setHubSession(null);
  closeUserSwitch();
  deviceMode.value = 'shared';
  deviceTrusted.value = false;
  pinPolicy.value = 'per_shift';
  replace.mockClear();
  loadDeviceMode.mockClear();
});

describe('the hand-over entry in the user menu', () => {
  it('is offered on the counter till, right beside «Sign out»', async () => {
    seedCounterTill();
    const wrapper = await mountShell();

    const entry = wrapper.find('[data-testid="switch-user-item"]');
    expect(entry.exists()).toBe(true);
    expect(entry.text()).toBe(en.userSwitch.menu);
  });

  it('is not offered on somebody’s own device', async () => {
    // A `personal` device has one user by definition (hub#358): there is nobody to hand over to,
    // and the grid of faces would publish the staff list on a device that never asks for a PIN.
    seedCounterTill();
    deviceMode.value = 'personal';
    const wrapper = await mountShell();

    expect(wrapper.find('[data-testid="switch-user-item"]').exists()).toBe(false);
  });

  it('is not offered on a till the hub never enrolled', async () => {
    // Without device-trust the PIN cannot work at all (§2.9, hub#330): the entry would be a button
    // that always fails.
    seedCounterTill();
    deviceTrusted.value = false;
    const wrapper = await mountShell();

    expect(wrapper.find('[data-testid="switch-user-item"]').exists()).toBe(false);
  });

  it('opens the overlay without navigating or signing anybody out', async () => {
    // The whole point of hub#456's second half: `login.changeUser` walks back to the grid of faces
    // OUTSIDE the session, and the sale on screen goes with it.
    seedCounterTill();
    const wrapper = await mountShell();

    await wrapper.find('[data-testid="switch-user-item"]').trigger('click');
    await flushPromises();

    expect(userSwitchOpen.value).toBe(true);
    expect(replace, 'the shell navigated away from the sale').not.toHaveBeenCalled();
    expect(localStorage.getItem('erplora.hub_session'), 'the till was signed out').toBe('sess-nacho');
  });
});

describe('the overlay itself', () => {
  it('is mounted over the shell, inside the authenticated chrome', async () => {
    // Mounted once and by the shell — not by a screen and not by a module — so the gesture exists
    // wherever the cashier happens to be when the shift changes.
    seedCounterTill();
    const wrapper = await mountShell();

    expect(wrapper.findComponent({ name: 'UserSwitchOverlay' }).exists()).toBe(true);
  });

  it('is not mounted where there is no session to hand over', async () => {
    const wrapper = await mountShell();
    expect(wrapper.findComponent({ name: 'UserSwitchOverlay' }).exists()).toBe(false);
  });
});

describe('what kind of device this is', () => {
  it('is asked again from inside the session, not only at the login screen', async () => {
    // `loadDeviceMode` used to run only in `LoginPage`. Reload a till with a live session and the
    // shell believed «not enrolled» for the rest of the day — the entry would never appear, and
    // the idle detector (hub#628) would read a stale dial too.
    seedCounterTill();
    await mountShell();

    expect(loadDeviceMode).toHaveBeenCalled();
  });
});
