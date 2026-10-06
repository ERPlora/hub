// @vitest-environment happy-dom
// hub#2506 — **on a shared till, nobody inherits somebody else's erplora.com credentials.**
//
// Reproduced on a bench (runtime + shell + a fake erplora.com): Anna types her password, erplora.com
// accepts it, the hub refuses her session afterwards (she is no longer a member). The screen says
// «Could not sign in» — and leaves `erplora.access`/`erplora.refresh` in the browser, because they
// were written BEFORE the hub was asked. Demo then signs in with his PIN on the same till and every
// request of his shift (30 on the bench, `/api/entitlement` among them) carries `Bearer <Anna's>`:
// his plan, invoices and «Manage account» are resolved with her account.
//
// Two rules close it, and this suite pins both through the screen, against the REAL token store:
//   1. an account sign-in that does not finish leaves no erplora.com credentials behind;
//   2. a PIN or badge session never carries them — whatever an earlier attempt left is cleared.
// And the positive control: an account sign-in that finishes keeps its credentials (the fix must
// not be «never store them»).
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

// The network is mocked; the token store is the real one (`setTokens`, `clearTokens`,
// `getAccessToken` over `localStorage`), so the assertions read what the next request would send.
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
import {
  cloudLogin,
  getAccessToken,
  runtimeBadgeLogin,
  runtimeCloudSession,
  runtimePinLogin,
  setTokens,
} from '../lib/cloud';

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {} } });

const ANNA = {
  access: 'anna-access-token',
  refresh: 'anna-refresh-token',
  user: { id: 'cloud-anna', name: 'Anna Cloud', email: 'anna@example.com' },
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

/** The counter till: people with a PIN and a device the hub already trusts. */
function seedCounterTill(): void {
  pinUsers.value = [{ id: 'demo', name: 'Demo', role: 'employee' }];
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

async function signInWithAccount(wrapper: Awaited<ReturnType<typeof mountLogin>>): Promise<void> {
  typeInto(wrapper, 'login-email', 'anna@example.com');
  typeInto(wrapper, 'login-password', 'secret-pass');
  await wrapper.vm.$nextTick();
  await wrapper.find('[data-testid="login-email-form"]').trigger('submit');
  await flushPromises();
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
  vi.mocked(cloudLogin).mockReset();
  vi.mocked(runtimeCloudSession).mockReset();
  vi.mocked(runtimePinLogin).mockReset();
  vi.mocked(runtimeBadgeLogin).mockReset();
});

describe('an account sign-in that does not finish', () => {
  it('leaves no erplora.com credentials behind when the hub refuses the session', async () => {
    vi.mocked(cloudLogin).mockResolvedValue({ ...ANNA, hubId: undefined });
    vi.mocked(runtimeCloudSession).mockRejectedValue(Object.assign(new Error('refused'), { code: 'not_a_member' }));
    const wrapper = await mountLogin();

    await signInWithAccount(wrapper);

    // The attempt really happened and really failed on the hub's side…
    expect(runtimeCloudSession).toHaveBeenCalledWith(ANNA.access, ANNA.user.name, ANNA.user.email);
    expect(wrapper.find('[data-testid="login-error"]').exists()).toBe(true);
    expect(replace).not.toHaveBeenCalled();
    // …and nothing of Anna's account is left for the next person on this till.
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem('erplora.refresh')).toBeNull();
  });

  it('does not leave an earlier person’s credentials behind either', async () => {
    // Somebody else's credentials were already on this till (an earlier attempt, a pass from the
    // panel). Bob's own attempt is refused by the hub: what stays must not be hers.
    setTokens('earlier-access', 'earlier-refresh');
    vi.mocked(cloudLogin).mockResolvedValue({ ...ANNA, hubId: undefined });
    vi.mocked(runtimeCloudSession).mockRejectedValue(Object.assign(new Error('refused'), { code: 'not_a_member' }));
    const wrapper = await mountLogin();

    await signInWithAccount(wrapper);

    expect(wrapper.find('[data-testid="login-error"]').exists()).toBe(true);
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem('erplora.refresh')).toBeNull();
  });

  it('keeps the credentials of an account sign-in that finishes (positive control)', async () => {
    vi.mocked(cloudLogin).mockResolvedValue({ ...ANNA, hubId: undefined });
    vi.mocked(runtimeCloudSession).mockResolvedValue({
      token: 'sess-anna',
      credential_kind: 'cloud',
      user: { id: 'u-anna', name: 'Anna Cloud', role: 'admin' },
      permissions: ['*'],
    } as never);
    const wrapper = await mountLogin();

    await signInWithAccount(wrapper);

    expect(replace).toHaveBeenCalled();
    expect(getAccessToken()).toBe(ANNA.access);
    expect(localStorage.getItem('erplora.refresh')).toBe(ANNA.refresh);
  });
});

describe('a PIN or badge session never carries erplora.com credentials', () => {
  it('clears what an earlier account attempt left when somebody signs in with a PIN', async () => {
    seedCounterTill();
    setTokens(ANNA.access, ANNA.refresh);
    vi.mocked(runtimePinLogin).mockResolvedValue({
      token: 'sess-demo',
      credential_kind: 'pin',
      user: { id: 'demo', name: 'Demo', role: 'employee' },
      permissions: ['sales.view'],
    } as never);
    const wrapper = await mountLogin();

    wrapper
      .find('ok-pinpad')
      .element.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '000000' }, bubbles: true }));
    await flushPromises();

    expect(runtimePinLogin).toHaveBeenCalledWith('Demo', '000000');
    expect(replace).toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem('erplora.refresh')).toBeNull();
  });

  it('keeps them when the PIN is refused: nobody new is in, nothing changes hands', async () => {
    seedCounterTill();
    setTokens(ANNA.access, ANNA.refresh);
    vi.mocked(runtimePinLogin).mockRejectedValue(new Error('refused'));
    const wrapper = await mountLogin();

    wrapper
      .find('ok-pinpad')
      .element.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '111111' }, bubbles: true }));
    await flushPromises();

    expect(replace).not.toHaveBeenCalled();
    expect(getAccessToken()).toBe(ANNA.access);
  });

  it('clears them when somebody signs in by swiping a badge', async () => {
    const uninstall = installBadgeScanner();
    try {
      seedCounterTill();
      setTokens(ANNA.access, ANNA.refresh);
      vi.mocked(runtimeBadgeLogin).mockResolvedValue({
        token: 'sess-badge',
        credential_kind: 'badge',
        user: { id: 'demo', name: 'Demo', role: 'employee' },
        permissions: ['sales.view'],
      } as never);
      await mountLogin();

      for (const ch of '0009171456') {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true }));
      }
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
      await flushPromises();

      expect(runtimeBadgeLogin).toHaveBeenCalledWith('0009171456');
      expect(replace).toHaveBeenCalled();
      expect(getAccessToken()).toBeNull();
    } finally {
      uninstall();
    }
  });
});
