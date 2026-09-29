// @vitest-environment happy-dom
// hub#2283 — **a locked pinpad says «wait», not «Incorrect PIN»**.
//
// After too many failed PINs the runtime stops taking PINs for a few minutes (the lock per name of
// hub#329 and, with hub#2282, the one per address) and answers `429 {code: "too_many_attempts",
// retry_after_secs}`. This screen only knew the two device-trust codes, so the lock fell through to
// «Incorrect PIN» — also for the person typing the RIGHT PIN, who retypes it, reads the same thing
// again and concludes they forgot it or the till is broken. Square, Toast and the phone lock
// screens all say the same thing here: too many attempts, try again in N minutes.
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
import { deviceTrusted } from '../lib/device-mode';
import { runtimePinLogin } from '../lib/cloud';
import { STRICT_PIN_POLICY, pinPolicy } from '../lib/pin-policy';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

// The real catalogues: what this asserts is that the SCREEN picks the right sentence, so
// putting invented strings in here would only prove the test can read its own fixture.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

/** A till the screen is willing to paint a pinpad on. */
function seedTill(): void {
  localStorage.setItem('erplora.trusted', '1');
  localStorage.setItem(
    'erplora.trusted_users',
    JSON.stringify([{ id: 'u1', name: 'Marta Ruiz', email: 'marta@bar.example', initials: 'MR' }]),
  );
  pinUsers.value = [{ id: 'u1', name: 'Marta Ruiz', role: 'employee' }];
  hubContextReady.value = true;
  machineRegistrationRequired.value = false;
  deviceTrusted.value = true;
}

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

/** A refusal shaped like `RuntimeError`: a message, the stable `code` and, on a lock, the wait. */
function refusal(code?: string, retryAfterSecs?: number): Error & { code?: string; retryAfterSecs?: number } {
  const err = new Error('refused') as Error & { code?: string; retryAfterSecs?: number };
  if (code) err.code = code;
  if (retryAfterSecs !== undefined) err.retryAfterSecs = retryAfterSecs;
  return err;
}

/** The sentence the catalogue gives for a lock of `minutes`, in the active locale. */
function lockSentence(minutes: number): string {
  return i18n.global.t('login.pinTooManyAttempts', { minutes }, minutes);
}

/** Type a PIN on the pinpad and let the promise settle. */
async function typePin(wrapper: Awaited<ReturnType<typeof mountLogin>>): Promise<void> {
  const pinpad = wrapper.find('ok-pinpad');
  pinpad.element.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '1234' }, bubbles: true }));
  await flushPromises();
}

beforeEach(() => {
  localStorage.clear();
  pinPolicy.value = STRICT_PIN_POLICY;
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
  vi.mocked(runtimePinLogin).mockReset();
  i18n.global.locale.value = 'en';
});

describe('a pinpad locked by too many failed attempts', () => {
  it('says how many minutes to wait, and NOT that the PIN is wrong', async () => {
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('too_many_attempts', 240));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    const text = wrapper.text();
    expect(text).toContain(lockSentence(4));
    expect(lockSentence(4)).toContain('4');
    expect(text).not.toContain(en.login.pinIncorrect);
  });

  it('rounds a part-minute UP, so the person never retries before the lock lifts', async () => {
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('too_many_attempts', 61));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    expect(wrapper.text()).toContain(lockSentence(2));
  });

  it.each(['en', 'es'] as const)(
    'says one minute, in the singular, for the last seconds of the lock (%s)',
    async (locale) => {
      i18n.global.locale.value = locale;
      seedTill();
      vi.mocked(runtimePinLogin).mockRejectedValue(refusal('too_many_attempts', 20));

      const wrapper = await mountLogin();
      await typePin(wrapper);

      expect(wrapper.text()).toContain(lockSentence(1));
      expect(lockSentence(1)).not.toBe(lockSentence(2).replace('2', '1'));
    },
  );

  it('never says «wait 0 minutes» when the lock is lifting right now', async () => {
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('too_many_attempts', 0));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    expect(wrapper.text()).toContain(lockSentence(1));
  });

  it('still says «wait» when the hub did not name the wait', async () => {
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('too_many_attempts'));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    const text = wrapper.text();
    expect(text).toContain(en.login.pinTooManyAttemptsNoWait);
    expect(text).not.toContain(en.login.pinIncorrect);
  });

  it('is said in Spanish on a Spanish till', async () => {
    i18n.global.locale.value = 'es';
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('too_many_attempts', 300));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    const text = wrapper.text();
    expect(text).toContain(lockSentence(5));
    expect(lockSentence(5)).not.toBe(
      i18n.global.t('login.pinTooManyAttempts', { minutes: 5 }, { locale: 'en', plural: 5 }),
    );
    expect(text).not.toContain(es.login.pinIncorrect);
  });

  it('does not leave the wait under a later, ordinary wrong PIN', async () => {
    // Once the lock lifts, a mistyped PIN is a mistyped PIN again: a stale «wait 4 minutes» would
    // send the person away from a pinpad that works.
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('too_many_attempts', 240));
    const wrapper = await mountLogin();
    await typePin(wrapper);
    expect(wrapper.text()).toContain(lockSentence(4));

    vi.mocked(runtimePinLogin).mockRejectedValue(refusal());
    await typePin(wrapper);

    const text = wrapper.text();
    expect(text).toContain(en.login.pinIncorrect);
    expect(text).not.toContain(lockSentence(4));
  });
});
