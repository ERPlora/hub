// @vitest-environment happy-dom
// ERPlora/hub#2510 — **signing in on a browser the hub did not trust yet keeps the PIN you have**.
//
// The boot context now names the team only to a live session or a device the PIN door trusts. A
// browser that was not trusted at boot therefore starts with an EMPTY list of faces. Signing in
// with the account and «Trust this device» makes it trusted, and the screen then asks «does this
// person already have a PIN?» against that list (hub#772). Read stale, the answer is always «no»:
// somebody who already has a PIN would be sent to «Create your access PIN» and their PIN reset.
//
// So, right after the hub hands out the session and before that question, the screen re-reads the
// context with the new session (`refreshHubIdentity`) and the answer comes from the list the hub
// gives to whoever is in.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

const replace = vi.fn();

vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  const pinUsers = ref<Array<{ id: string; name: string; role: string }>>([]);
  return {
    pinUsers,
    hubContextReady: ref(true),
    machineRegistered: ref(true),
    machineRegistrationRequired: ref(false),
    // With the session, the hub names the team: Marta already has a PIN.
    refreshHubIdentity: vi.fn(async () => {
      pinUsers.value = [{ id: 'u-marta', name: 'Marta Ruiz', role: 'employee' }];
    }),
  };
});

vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  const actual = await vi.importActual<typeof import('../lib/device-mode')>('../lib/device-mode');
  const deviceMode = ref<'shared' | 'personal'>('shared');
  const deviceTrusted = ref(false);
  return {
    deviceMode,
    deviceTrusted,
    deviceModeReady: ref(true),
    // The account sign-in made this device trusted.
    loadDeviceMode: vi.fn(async () => {
      deviceTrusted.value = true;
      return deviceMode.value;
    }),
    setDeviceMode: vi.fn(),
    offersPinLogin: actual.offersPinLogin,
  };
});

vi.mock('../lib/session', () => ({
  setUser: vi.fn(),
  setHubSession: vi.fn(),
  getHubSession: vi.fn(() => null),
}));
vi.mock('../lib/cloud', () => ({
  cloudLogin: vi.fn(async () => ({
    access: 'jwt-a',
    refresh: 'jwt-r',
    hubId: 'hub-1',
    user: { id: 'cloud-marta', name: 'Marta Ruiz', email: 'marta@bar.example' },
  })),
  cloudLogin2fa: vi.fn(),
  TwoFactorRequiredError: class TwoFactorRequiredError extends Error {
    ticket = '';
  },
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  runtimeCloudSession: vi.fn(async () => ({
    token: 'sess-1',
    credential_kind: 'cloud',
    user: { id: 'u-marta', role: 'employee' },
    permissions: [],
  })),
  runtimePinLogin: vi.fn(),
  runtimeSetPin: vi.fn(),
  googleLoginUrl: vi.fn(() => 'https://example.invalid/oauth'),
  exchangeGoogleCode: vi.fn(),
}));
vi.mock('../lib/config', () => ({ config: { hubId: '', demo: false } }));
vi.mock('../lib/theme', () => ({ isDark: ref(false), toggleTheme: vi.fn() }));
vi.mock('../lib/branding', () => ({ hubLogo: ref('/logo.svg'), DEFAULT_HUB_LOGO: '/logo.svg' }));
vi.mock('vue-router', () => ({
  useRouter: () => ({ currentRoute: { value: { query: {} } }, replace }),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import LoginPage from './LoginPage.vue';
import { refreshHubIdentity } from '../lib/runtime';
import { runtimeSetPin } from '../lib/cloud';
import { STRICT_PIN_POLICY, pinPolicy } from '../lib/pin-policy';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

async function signInWithTheAccount() {
  const wrapper = mount(LoginPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
      stubs: { IonPopover: true },
    },
  });
  await flushPromises();
  const form = wrapper.find('form[data-testid="login-email-form"]');
  expect(form.exists()).toBe(true);
  const [email, password] = form.findAll('ion-input');
  for (const [input, value] of [
    [email, 'marta@bar.example'],
    [password, 'secret'],
  ] as const) {
    input.element.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
  }
  await form.trigger('submit');
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  localStorage.clear();
  pinPolicy.value = STRICT_PIN_POLICY;
  replace.mockClear();
  vi.mocked(refreshHubIdentity).mockClear();
});

describe('hub#2510 — an account sign-in on a browser that was not trusted at boot', () => {
  it('re-reads the faces with the new session and lets a person who has a PIN straight in', async () => {
    const wrapper = await signInWithTheAccount();

    expect(refreshHubIdentity).toHaveBeenCalledTimes(1);
    // Not sent to «Create your access PIN»: the PIN Marta already has is kept.
    expect(wrapper.find('[data-testid="login-setup-step"]').exists()).toBe(false);
    expect(runtimeSetPin).not.toHaveBeenCalled();
    expect(replace).toHaveBeenCalledTimes(1);
  });
});
