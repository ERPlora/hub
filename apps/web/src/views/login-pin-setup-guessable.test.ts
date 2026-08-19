// @vitest-environment happy-dom
// PIN setup after the first account login (§2.9) — hub#974.
//
// The runtime now refuses a guessable PIN (`0000`, `1234`) at `POST /api/auth/set-pin`, the same
// rule Personal applies. The login screen used to send whatever was typed and, on refusal, say
// «the PIN could not be saved» — true, useless. Mirror the check here (like `localUserIssue` does
// for Personal), name the reason, and never call the runtime for a PIN it will refuse.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return {
    pinUsers: ref([]),
    hubContextReady: ref(true),
    machineRegistered: ref(true),
    machineRegistrationRequired: ref(false),
  };
});
vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  const actual = await vi.importActual<typeof import('../lib/device-mode')>('../lib/device-mode');
  return {
    deviceMode: ref('shared'),
    deviceTrusted: ref(true),
    deviceModeReady: ref(true),
    loadDeviceMode: vi.fn(async () => 'shared'),
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
  runtimeSetPin: vi.fn(async () => undefined),
  googleLoginUrl: vi.fn(() => 'https://example.invalid/oauth'),
  exchangeGoogleCode: vi.fn(),
}));
vi.mock('../lib/config', () => ({ config: { hubId: 'hub-1', demo: false } }));
vi.mock('../lib/theme', () => ({ isDark: ref(false), toggleTheme: vi.fn() }));
vi.mock('../lib/branding', () => ({ hubLogo: ref('/logo.svg'), DEFAULT_HUB_LOGO: '/logo.svg' }));
vi.mock('vue-router', () => ({
  useRouter: () => ({ currentRoute: { value: { query: {} } }, replace: vi.fn() }),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import LoginPage from './LoginPage.vue';
import { runtimeSetPin } from '../lib/cloud';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      login: {
        setupSaveError: 'The PIN could not be saved. Please try again.',
        setupPinTooSimple:
          'That PIN is too easy to guess: avoid repeated digits (1111) and straight runs (1234).',
      },
    },
  },
});

type Login = {
  onSetupComplete: (pin: string) => Promise<void>;
  setupErrorMessage: string;
  setupPhase: string;
};

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
  vi.mocked(runtimeSetPin).mockClear();
});

describe('choosing a PIN after the first account login', () => {
  it('refuses a guessable PIN with its reason and never sends it to the runtime', async () => {
    const wrapper = await mountLogin();
    const vm = wrapper.vm as unknown as Login;
    await vm.onSetupComplete('1234'); // first entry
    await vm.onSetupComplete('1234'); // confirmation
    await flushPromises();

    expect(vi.mocked(runtimeSetPin)).not.toHaveBeenCalled();
    expect(vm.setupErrorMessage).toContain('too easy to guess');
    expect(vm.setupPhase).toBe('first');
  });

  it('still saves a PIN that is not guessable (the control)', async () => {
    const wrapper = await mountLogin();
    const vm = wrapper.vm as unknown as Login;
    await vm.onSetupComplete('2580');
    await vm.onSetupComplete('2580');
    await flushPromises();

    expect(vi.mocked(runtimeSetPin)).toHaveBeenCalledWith('2580', 'sess-1');
  });
});
