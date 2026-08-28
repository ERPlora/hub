// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1302.
//
// Ioan hit this on a NEW hub (`qa-pre-dos.a.erplora.com`, PIN length 6 since hub#1037 — every new
// hub starts on 6): the first-user setup screen said «Elige un PIN de 4 dígitos» while the pinpad
// underneath it already asked for six (`:length="hubPinLength"`, `lib/pin-length.ts`). Somebody
// who typed exactly what the screen told them to filled four dots, nothing happened, and only the
// fifth and sixth digit moved the screen to «Confirma tu PIN».
//
// The pinpad's `:length` binding was already correct (verified by reading `LoginPage.vue` before
// writing this test) — the bug was purely the static "4" in the hint text. This test pins the
// text to `hubPinLength`, and proves the pinpad genuinely will not complete on four digits when
// the hub wants six.
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
import { hubSettings } from '../lib/hub-settings';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      login: {
        setupChoosePin: 'Choose a {n}-digit PIN',
        setupConfirmPin: 'Confirm your PIN',
      },
    },
  },
});

type Login = { step: string };

async function mountAtSetup() {
  const wrapper = mount(LoginPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
      stubs: { IonPopover: true },
    },
  });
  await flushPromises();
  // Reached in production only after an email login with "trust this device" and no PIN yet
  // (`LoginPage.vue`, `if (trust.value) { ... step.value = 'setup'; }`). The watcher that could
  // otherwise reset `step` explicitly skips while it is `'setup'`, so setting it directly here is
  // stable — it is the same state the real flow lands in, reached the short way.
  (wrapper.vm as unknown as Login).step = 'setup';
  await flushPromises();
  return wrapper;
}

describe('hub#1302 — the PIN setup hint always names THIS hub\'s PIN length', () => {
  beforeEach(() => {
    hubSettings.value = null;
  });

  it('says 6 and wires a 6-long pinpad for a hub whose PIN is 6 (hub#1037 default for new hubs)', async () => {
    hubSettings.value = { pin_length: 6 } as never;
    const wrapper = await mountAtSetup();

    expect(wrapper.text()).toContain('Choose a 6-digit PIN');
    expect(wrapper.text()).not.toContain('4-digit');
    expect(wrapper.get('ok-pinpad').attributes('length')).toBe('6');
  });

  it('says 4 for a hub still on the compatibility default', async () => {
    hubSettings.value = { pin_length: 4 } as never;
    const wrapper = await mountAtSetup();

    expect(wrapper.text()).toContain('Choose a 4-digit PIN');
    expect(wrapper.get('ok-pinpad').attributes('length')).toBe('4');
  });
});
