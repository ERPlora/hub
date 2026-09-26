// @vitest-environment happy-dom
// hub#2152 — the login screen says why it is there when the panel's pass could not be redeemed.
//
// The person clicked «open» in the ERPlora panel and expected to land inside the hub. When the
// exchange fails the shell falls back to the login (it must: that is the way in that still works),
// but until now it did so in silence, so the reading closest to hand was «my password is gone» or
// «the hub is broken». `main.ts` leaves a one-shot flag (`takeCourierFailure`) and this screen
// turns it into a short notice from the catalogue — in English and Spanish, never a raw code.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';


vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return {
    pinUsers: ref<Array<{ id: string; name: string; role: string }>>([]),
    hubContextReady: ref(true),
    machineRegistered: ref(true),
    machineRegistrationRequired: ref(false),
  };
});

vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  const actual = await vi.importActual<typeof import('../lib/device-mode')>('../lib/device-mode');
  return {
    deviceMode: ref<'shared' | 'personal'>('shared'),
    deviceTrusted: ref(false),
    deviceModeReady: ref(true),
    loadDeviceMode: vi.fn(async () => 'shared' as const),
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
  cloudLogin: vi.fn(),
  cloudLogin2fa: vi.fn(),
  TwoFactorRequiredError: class TwoFactorRequiredError extends Error {
    ticket = '';
  },
  setTokens: vi.fn(),
  runtimeBadgeLogin: vi.fn(),
  runtimeCloudSession: vi.fn(),
  runtimePinLogin: vi.fn(),
  runtimeSetPin: vi.fn(),
  googleLoginUrl: vi.fn(() => 'https://example.invalid/oauth'),
  exchangeGoogleCode: vi.fn(),
}));
vi.mock('../lib/config', () => ({
  config: { hubId: 'hub-1', demo: false, cloudApiUrl: 'https://saas.example.invalid' },
}));
vi.mock('../lib/theme', () => ({ isDark: ref(false), toggleTheme: vi.fn() }));
vi.mock('../lib/branding', () => ({ hubLogo: ref('/logo.svg'), DEFAULT_HUB_LOGO: '/logo.svg' }));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

// `vi.mock` factories are hoisted above every `const` in the file, so the doubles they close over
// have to be hoisted too — otherwise the module under test imports a name that does not exist yet.
const doubles = vi.hoisted(() => ({
  /** Which binary is this: the browser (no Tauri) by default, a store copy when a test says so. */
  distribution: { value: null as string | null },
  query: { value: {} as Record<string, string> },
  openExternal: vi.fn(async (_url: string) => {}),
  saasDoor: vi.fn(async (_path: string, url: string, _purpose: string) => url),
}));

vi.mock('../lib/device', () => ({
  getDeviceContext: vi.fn(async () =>
    doubles.distribution.value ? { distribution: doubles.distribution.value } : null,
  ),
}));
vi.mock('../lib/open-external', () => ({ openExternal: doubles.openExternal }));
vi.mock('../lib/saas-door', () => ({ saasDoor: doubles.saasDoor }));
vi.mock('vue-router', () => ({
  useRouter: () => ({
    currentRoute: { value: { query: doubles.query.value } },
    replace: vi.fn(),
    push: vi.fn(),
  }),
}));

const courierState = vi.hoisted(() => ({ failed: false }));
vi.mock('../lib/courier', () => ({
  takeCourierFailure: vi.fn(() => {
    const failed = courierState.failed;
    courierState.failed = false;
    return failed;
  }),
}));

const { distribution, query } = doubles;

import LoginPage from './LoginPage.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

// The REAL catalogues: what is asserted is that the SCREEN picks the right sentence. Invented
// strings in a fixture would only prove the test can read itself.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
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
  query.value = {};
  distribution.value = null;
  courierState.failed = false;
  i18n.global.locale.value = 'en';
});

describe('the login screen explains a pass it could not redeem (hub#2152)', () => {
  it('says the panel could not sign the person in, in the words of the catalogue', async () => {
    courierState.failed = true;

    const notice = (await mountLogin()).find('[data-testid="login-courier-failed"]');

    expect(notice.exists()).toBe(true);
    expect(notice.attributes('heading')).toBe(en.login.courierFailed);
    expect(notice.text()).toContain(en.login.courierFailedBody);
  });

  it('reads in Spanish too (ADR-0055/0199)', async () => {
    courierState.failed = true;
    i18n.global.locale.value = 'es';

    const notice = (await mountLogin()).find('[data-testid="login-courier-failed"]');

    expect(notice.attributes('heading')).toBe(es.login.courierFailed);
    expect(notice.text()).toContain(es.login.courierFailedBody);
    expect(es.login.courierFailed).not.toBe(en.login.courierFailed);
    expect(es.login.courierFailedBody).not.toBe(en.login.courierFailedBody);
  });

  it('paints nothing on an ordinary visit to the login', async () => {
    const wrapper = await mountLogin();

    expect(wrapper.find('[data-testid="login-courier-failed"]').exists()).toBe(false);
  });

  it('is a one-shot notice: coming back to the login later does not repeat it', async () => {
    courierState.failed = true;
    await mountLogin();

    const again = await mountLogin();

    expect(again.find('[data-testid="login-courier-failed"]').exists()).toBe(false);
  });
});
