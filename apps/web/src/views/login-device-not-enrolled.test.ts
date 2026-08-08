// @vitest-environment happy-dom
// hub#330 — **the refusal has to be readable**, now that device-trust is armed by default.
//
// The gate itself was closed in PR #383: with `HUB_DEVICE_TRUST` armed, a PIN login from a device
// that never signed in with an account here is refused (`403 device_untrusted`), and one that names
// no device at all is refused too (`device_unidentified`). Arming it by default is the other half
// of the issue — and on its own it would have been an outage, because of what this screen did with
// the refusal:
//
// ```js
// } catch { pinError.value = true; ... }   // ← every failure is "Incorrect PIN"
// ```
//
// The catch swallowed the reason. So the first person to reach a new till would have typed a PIN
// that IS correct, been told it was wrong, and typed it again — with no sentence anywhere on the
// screen naming the one gesture that fixes it (sign in once with an account, here). "It says my PIN
// is wrong and it isn't" is a support call, and it is indistinguishable from a real bug.
//
// Two things this suite pins down:
//
//  1. **Each refusal says its own thing**, and neither is «Incorrect PIN».
//  2. **A wrong PIN still says «Incorrect PIN»** — the new branch must not eat the ordinary case,
//     which is the failure this screen exists to report and by far the most common one.
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
  return {
    deviceMode,
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
import { runtimePinLogin } from '../lib/cloud';
import { STRICT_PIN_POLICY, pinPolicy } from '../lib/pin-policy';
import en from '../i18n/locales/en';

// The real English catalogue: what this asserts is that the SCREEN picks the right sentence, so
// putting invented strings in here would only prove the test can read its own fixture.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
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

/** A refusal shaped like the runtime's: a message plus the stable `code`. */
function refusal(code?: string): Error & { code?: string } {
  const err = new Error('refused') as Error & { code?: string };
  if (code) err.code = code;
  return err;
}

/** Type a PIN on the pinpad and let the promise settle. */
async function typePin(wrapper: Awaited<ReturnType<typeof mountLogin>>): Promise<void> {
  const pinpad = wrapper.find('ok-pinpad');
  pinpad.element.dispatchEvent(
    new CustomEvent('ok-complete', { detail: { value: '1234' }, bubbles: true }),
  );
  await flushPromises();
}

beforeEach(() => {
  localStorage.clear();
  pinPolicy.value = STRICT_PIN_POLICY;
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
  vi.mocked(runtimePinLogin).mockReset();
});

describe('a device that has not signed in with an account here', () => {
  it('is told to do that, and is NOT told its PIN is wrong', async () => {
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('device_untrusted'));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    const text = wrapper.text();
    expect(text).toContain(en.login.deviceNotEnrolled);
    expect(text).not.toContain(en.login.pinIncorrect);
  });

  it('names the gesture that fixes it, not the mechanism that refused', async () => {
    // The sentence is read by somebody standing at a till who has no idea what device-trust is. It
    // has to say what to DO. And it may not reach for the platform's nouns — the vocabulary
    // contract of hub#365 (`i18n/login-to-till-vocabulary.test.ts`) covers every key here.
    expect(en.login.deviceNotEnrolled.toLowerCase()).toContain('account');
    expect(en.login.deviceNotEnrolled).not.toMatch(/device-trust|token|403/i);
  });
});

describe('a client that cannot name its device at all', () => {
  it('gets its own sentence — the fix is not the same one', async () => {
    // This is the browser whose site storage is blocked (a private window, Safari with data off).
    // Telling that person to "sign in with an account once here" would be a lie: they can, and the
    // pinpad still will not work, because nothing survives the page. So it is a different sentence.
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('device_unidentified'));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    const text = wrapper.text();
    expect(text).toContain(en.login.deviceUnidentified);
    expect(text).not.toContain(en.login.deviceNotEnrolled);
    expect(text).not.toContain(en.login.pinIncorrect);
  });
});

describe('the ordinary wrong PIN', () => {
  it('still says the PIN is incorrect', async () => {
    // The regression this pair of branches invites: a new `if` that catches everything and turns
    // every mistyped digit into a lecture about devices.
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal());

    const wrapper = await mountLogin();
    await typePin(wrapper);

    const text = wrapper.text();
    expect(text).toContain(en.login.pinIncorrect);
    expect(text).not.toContain(en.login.deviceNotEnrolled);
    expect(text).not.toContain(en.login.deviceUnidentified);
  });

  it('says it for a code the hub invented after this build shipped', async () => {
    // Fail towards the sentence that is always true ("that did not work"), never towards an
    // instruction that might be wrong. A build that met `device_stolen` must not guess.
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('some_code_from_the_future'));

    const wrapper = await mountLogin();
    await typePin(wrapper);

    expect(wrapper.text()).toContain(en.login.pinIncorrect);
  });
});

describe('trying again', () => {
  it('clears the device message once the PIN goes through', async () => {
    // The owner signs in with their account on the till, comes back, and types the PIN. A stale
    // red sentence under a pinpad that now works is its own support call.
    seedTill();
    vi.mocked(runtimePinLogin).mockRejectedValue(refusal('device_untrusted'));
    const wrapper = await mountLogin();
    await typePin(wrapper);
    expect(wrapper.text()).toContain(en.login.deviceNotEnrolled);

    vi.mocked(runtimePinLogin).mockResolvedValue({
      token: 't',
      user: { id: 'u1', role: 'employee' },
      permissions: [],
    } as never);
    await typePin(wrapper);

    expect(wrapper.text()).not.toContain(en.login.deviceNotEnrolled);
  });
});
