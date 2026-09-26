// @vitest-environment happy-dom
// hub#2189 — **the login screen promised «personal» on a device nobody had called personal.**
//
// The note «This device is set up as personal: it stays signed in and never asks for a PIN» hung
// from `v-else` of «is the pinpad offered?». But the pinpad is also withheld from a counter till
// that simply has not been trusted yet (hub#514: a fresh browser, a new tablet) and from a hub
// whose dial says «never». On those devices the screen told the person it would never ask for a
// PIN — and, with the «trust this device» box hidden but still ticked underneath, the login they
// were about to do trusted the device and the next visit opened on «Enter your PIN».
//
// The rule these tests pin down: the note is said ONLY where the hub answered `personal`, and a
// shared device that will ask for the PIN once trusted OFFERS the trust box instead of ticking it
// silently.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return {
    pinUsers: ref<Array<{ id: string; name: string; role: string }>>([]),
    hubContextReady: ref(false),
    machineRegistered: ref(true),
    machineRegistrationRequired: ref(false),
  };
});

// The mode itself is the real rule (`offersPinLogin`); only the hub's ANSWER is a double, because
// what is under test is what the screen does with it.
vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  const actual = await vi.importActual<typeof import('../lib/device-mode')>('../lib/device-mode');
  const deviceMode = ref<'shared' | 'personal'>('shared');
  const deviceTrusted = ref(false);
  return {
    deviceMode,
    deviceTrusted,
    deviceModeReady: ref(true),
    loadDeviceMode: vi.fn(async () => deviceMode.value),
    setDeviceMode: vi.fn(),
    offersPinLogin: actual.offersPinLogin,
  };
});

vi.mock('../lib/session', () => ({
  setUser: vi.fn(),
  setHubSession: vi.fn(),
  getHubSession: vi.fn(() => 'sess-1'),
}));
vi.mock('../lib/cloud', () => ({
  cloudLogin: vi.fn(),
  cloudLogin2fa: vi.fn(),
  TwoFactorRequiredError: class TwoFactorRequiredError extends Error {
    ticket = '';
  },
  setTokens: vi.fn(),
  runtimeCloudSession: vi.fn(),
  runtimePinLogin: vi.fn(),
  runtimeSetPin: vi.fn(),
  googleLoginUrl: vi.fn(() => 'https://example.invalid/oauth'),
  exchangeGoogleCode: vi.fn(),
}));
vi.mock('../lib/config', () => ({ config: { hubId: 'hub-1', demo: false } }));
vi.mock('../lib/theme', () => ({ isDark: ref(false), toggleTheme: vi.fn() }));
vi.mock('../lib/branding', () => ({ hubLogo: ref('/logo.svg'), DEFAULT_HUB_LOGO: '/logo.svg' }));
vi.mock('vue-router', () => ({
  useRouter: () => ({
    currentRoute: { value: { query: {} } },
    replace: vi.fn(),
  }),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import LoginPage from './LoginPage.vue';
import { hubContextReady, machineRegistrationRequired, pinUsers } from '../lib/runtime';
import { deviceMode, deviceTrusted, loadDeviceMode } from '../lib/device-mode';
import { publishPinPolicy } from '../lib/pin-policy';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

async function mountLogin() {
  const wrapper = mount(LoginPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
      stubs: { IonPopover: true },
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  localStorage.clear();
  deviceMode.value = 'shared';
  deviceTrusted.value = false;
  publishPinPolicy('per_shift');
  vi.mocked(loadDeviceMode).mockClear();
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
});

describe('hub#2189 — the «personal» note is only said on a personal device', () => {
  it('a shared till that is not trusted yet does not claim to be personal, and offers the trust box', async () => {
    // A fresh browser at the counter: the hub answers `shared`, not trusted yet (hub#514).
    deviceMode.value = 'shared';
    deviceTrusted.value = false;
    hubContextReady.value = true;

    const wrapper = await mountLogin();

    expect(wrapper.find('ok-pinpad').exists()).toBe(false);
    expect(wrapper.html()).not.toContain('login.personalDeviceNote');
    // Signing in here is what arms the pinpad for next time: the person is asked, not ticked for.
    expect(wrapper.find('[data-testid="login-trust"]').exists()).toBe(true);
  });

  it('a shared device on a hub whose dial says «never» does not claim to be personal either', async () => {
    deviceMode.value = 'shared';
    deviceTrusted.value = true;
    hubContextReady.value = true;
    publishPinPolicy('never');

    const wrapper = await mountLogin();

    expect(wrapper.html()).not.toContain('login.personalDeviceNote');
    // No PIN will ever be asked here, so a box about arming one would change nothing.
    expect(wrapper.find('[data-testid="login-trust"]').exists()).toBe(false);
  });

  it('a personal device keeps its note and gets no trust box', async () => {
    deviceMode.value = 'personal';
    deviceTrusted.value = true;
    hubContextReady.value = true;

    const wrapper = await mountLogin();

    expect(wrapper.html()).toContain('login.personalDeviceNote');
    expect(wrapper.find('[data-testid="login-trust"]').exists()).toBe(false);
  });
});
