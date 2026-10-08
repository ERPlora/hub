// @vitest-environment happy-dom
// hub#2536 — **on a shared till, the PIN screen does not show the team's e-mail addresses.**
//
// The face grid of Acceso printed, under each name, the e-mail of anybody who had ever signed in
// with their erplora.com account in that browser. Whoever walked up to the till (a customer, a new
// hire) could read the whole team's addresses without signing in, and they survived signing out,
// removing the device and switching it to «personal». The hub never hands out an e-mail in its list
// of PIN people (HUB-F133): the leak was the screen's own copy in `erplora.trusted_users`.
//
// The rule, as Square and Toast do it: a face shows what you need to pick yourself — the name and
// its initials — and this browser stops keeping e-mails for the grid. The e-mail of whoever signs
// in with a PIN or a badge comes from the hub's profile (`/api/profile`, read by the shell after
// the sign-in), never from what this browser remembers about somebody.
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
    refreshHubIdentity: vi.fn(async () => {}),
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
    loadDeviceMode: vi.fn(async () => deviceMode.value),
    setDeviceMode: vi.fn(),
    offersPinLogin: actual.offersPinLogin,
  };
});

vi.mock('../lib/session', () => ({
  setUser: vi.fn(),
  setHubSession: vi.fn(),
  getHubSession: vi.fn(() => null),
}));

vi.mock('../lib/cloud', async () => {
  const actual = await vi.importActual<typeof import('../lib/cloud')>('../lib/cloud');
  return {
    setTokens: actual.setTokens,
    clearTokens: actual.clearTokens,
    getAccessToken: actual.getAccessToken,
    cloudLogin: vi.fn(),
    cloudLogin2fa: vi.fn(),
    TwoFactorRequiredError: class TwoFactorRequiredError extends Error {
      ticket = '';
    },
    runtimeCloudSession: vi.fn(),
    runtimePinLogin: vi.fn(),
    runtimeBadgeLogin: vi.fn(),
    runtimeSetPin: vi.fn(),
    googleLoginUrl: vi.fn(() => 'https://example.invalid/oauth'),
    exchangeGoogleCode: vi.fn(),
  };
});
vi.mock('../lib/config', () => ({ config: { hubId: 'hub-1', demo: false }, cloudApiUrlReady: async () => {} }));
vi.mock('../lib/theme', () => ({ isDark: ref(false), toggleTheme: vi.fn() }));
vi.mock('../lib/branding', () => ({ hubLogo: ref('/logo.svg'), DEFAULT_HUB_LOGO: '/logo.svg' }));
const replace = vi.fn();
vi.mock('vue-router', () => ({
  useRouter: () => ({ currentRoute: { value: { query: {} } }, replace: (...a: unknown[]) => replace(...a) }),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import LoginPage from './LoginPage.vue';
import { hubContextReady, machineRegistrationRequired, pinUsers } from '../lib/runtime';
import { deviceMode, deviceTrusted } from '../lib/device-mode';
import { STRICT_PIN_POLICY, pinPolicy } from '../lib/pin-policy';
import { installBadgeScanner } from '../lib/badge-scanner';
import { setUser } from '../lib/session';
import { cloudLogin, runtimeBadgeLogin, runtimeCloudSession, runtimePinLogin } from '../lib/cloud';

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } });

/** What a browser that predates this fix remembers: every face with its e-mail. */
const REMEMBERED_WITH_EMAILS = [
  { id: 'u-anna', name: 'Anna Cloud', email: 'anna@example.com', initials: 'AC' },
  { id: 'u-bob', name: 'Bob Till', email: 'bob@example.com', initials: 'BT' },
];

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

/** The counter till: two people with a PIN and a device the hub already trusts. */
function seedCounterTill(): void {
  pinUsers.value = [
    { id: 'u-anna', name: 'Anna Cloud', role: 'admin' },
    { id: 'u-bob', name: 'Bob Till', role: 'employee' },
  ];
  hubContextReady.value = true;
  machineRegistrationRequired.value = false;
  deviceTrusted.value = true;
  deviceMode.value = 'shared';
}

function typeInto(wrapper: Awaited<ReturnType<typeof mountLogin>>, testid: string, value: string): void {
  const el = wrapper.find(`[data-testid="${testid}"]`).element;
  el.dispatchEvent(new CustomEvent('ion-input', { detail: { value } }));
  el.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
}

beforeEach(() => {
  localStorage.clear();
  pinPolicy.value = STRICT_PIN_POLICY;
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
  deviceTrusted.value = false;
  deviceMode.value = 'shared';
  replace.mockClear();
  vi.mocked(setUser).mockClear();
  vi.mocked(cloudLogin).mockReset();
  vi.mocked(runtimeCloudSession).mockReset();
  vi.mocked(runtimePinLogin).mockReset();
  vi.mocked(runtimeBadgeLogin).mockReset();
});

describe('the face grid of a shared till', () => {
  it('shows each person by name, and nobody’s e-mail', async () => {
    localStorage.setItem('erplora.trusted_users', JSON.stringify(REMEMBERED_WITH_EMAILS));
    seedCounterTill();
    const wrapper = await mountLogin();

    const anna = wrapper.find('[data-testid="login-pin-user-u-anna"]');
    const bob = wrapper.find('[data-testid="login-pin-user-u-bob"]');
    // The grid is really on screen, with both faces (positive control)…
    expect(anna.text()).toContain('Anna Cloud');
    expect(bob.text()).toContain('Bob Till');
    // …and no address of the team is readable from it.
    expect(wrapper.html()).not.toContain('anna@example.com');
    expect(wrapper.html()).not.toContain('bob@example.com');
  });

  it('stops keeping the e-mails this browser remembered for the grid', async () => {
    localStorage.setItem('erplora.trusted_users', JSON.stringify(REMEMBERED_WITH_EMAILS));
    seedCounterTill();
    await mountLogin();

    const stored = JSON.parse(localStorage.getItem('erplora.trusted_users') ?? '[]') as Array<Record<string, unknown>>;
    // The faces are still remembered (the grid needs them)…
    expect(stored.map((u) => u.id)).toEqual(['u-anna', 'u-bob']);
    // …without their e-mails.
    expect(stored.some((u) => 'email' in u)).toBe(false);
  });
});

describe('signing in on a shared till', () => {
  it('remembers the face of an account sign-in without its e-mail', async () => {
    deviceTrusted.value = true;
    hubContextReady.value = true;
    vi.mocked(cloudLogin).mockResolvedValue({
      access: 'anna-access',
      refresh: 'anna-refresh',
      user: { id: 'cloud-anna', name: 'Anna Cloud', email: 'anna@example.com' },
      hubId: undefined,
    } as never);
    vi.mocked(runtimeCloudSession).mockResolvedValue({
      token: 'sess-anna',
      credential_kind: 'cloud',
      user: { id: 'u-anna', name: 'Anna Cloud', role: 'admin' },
      permissions: ['*'],
    } as never);
    const wrapper = await mountLogin();

    typeInto(wrapper, 'login-email', 'anna@example.com');
    typeInto(wrapper, 'login-password', 'secret-pass');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="login-email-form"]').trigger('submit');
    await flushPromises();

    // The sign-in really finished and the face was remembered for the grid (positive control)…
    expect(runtimeCloudSession).toHaveBeenCalled();
    const stored = JSON.parse(localStorage.getItem('erplora.trusted_users') ?? '[]') as Array<Record<string, unknown>>;
    expect(stored.map((u) => u.id)).toContain('u-anna');
    // …without the address.
    expect(localStorage.getItem('erplora.trusted_users')).not.toContain('anna@example.com');
  });

  it('takes the e-mail of a PIN sign-in from the hub, not from what this browser remembers', async () => {
    localStorage.setItem('erplora.trusted_users', JSON.stringify(REMEMBERED_WITH_EMAILS));
    seedCounterTill();
    vi.mocked(runtimePinLogin).mockResolvedValue({
      token: 'sess-bob',
      credential_kind: 'pin',
      user: { id: 'u-bob', name: 'Bob Till', role: 'employee' },
      permissions: ['sales.view'],
    } as never);
    const wrapper = await mountLogin();

    await wrapper.find('[data-testid="login-pin-user-u-bob"]').trigger('click');
    await flushPromises();
    wrapper
      .find('ok-pinpad')
      .element.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '000000' }, bubbles: true }));
    await flushPromises();

    expect(runtimePinLogin).toHaveBeenCalledWith('Bob Till', '000000');
    expect(setUser).toHaveBeenCalledWith(expect.objectContaining({ id: 'u-bob', email: '' }));
  });

  it('takes the e-mail of a badge sign-in from the hub, not from what this browser remembers', async () => {
    const uninstall = installBadgeScanner();
    try {
      localStorage.setItem('erplora.trusted_users', JSON.stringify(REMEMBERED_WITH_EMAILS));
      seedCounterTill();
      vi.mocked(runtimeBadgeLogin).mockResolvedValue({
        token: 'sess-bob',
        credential_kind: 'badge',
        user: { id: 'u-bob', name: 'Bob Till', role: 'employee' },
        permissions: ['sales.view'],
      } as never);
      await mountLogin();

      for (const ch of '0009171456') {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true }));
      }
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
      await flushPromises();

      expect(runtimeBadgeLogin).toHaveBeenCalledWith('0009171456');
      expect(setUser).toHaveBeenCalledWith(expect.objectContaining({ id: 'u-bob', email: '' }));
    } finally {
      uninstall();
    }
  });
});
