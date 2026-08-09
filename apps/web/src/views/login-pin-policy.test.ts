// @vitest-environment happy-dom
// hub#359 — **the dial the business set reaches the login screen**: "ask for a PIN: always / per
// shift / never".
//
// hub#358 made the pinpad hang off the DEVICE (`shared` vs `personal`). This is the second control,
// and it exists for the case the device mode cannot express: the one-person minimarket whose till
// is genuinely a shared counter till and who still does not want to type four digits to sell.
//
// The invariant is the same one, and it is the one that decides whether any of this is a lock:
//
// > **The screen READS the dial and never writes it.** It runs before any session exists. The write
// > door is `PUT /api/settings` behind an ADMIN session — if the screen in front of the lock could
// > turn the lock off, there would be no lock.
//
// And what `never` gives up is stated precisely, because it is easy to overstate: it stops the hub
// asking WHICH person is at the till. It does not leave the till open — the session still expires
// when the device says it does (the runtime composes both controls by the shorter window,
// `crates/runtime/tests/pin_policy.rs`), so somebody with a real account still has to open it.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';
import { readFileSync } from 'node:fs';

vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return {
    pinUsers: ref<Array<{ id: string; name: string; role: string }>>([]),
    hubContextReady: ref(false),
    machineRegistered: ref(true),
    machineRegistrationRequired: ref(false),
  };
});

// Only the hub's ANSWER is a double. `offersPinLogin` and the whole of `pin-policy.ts` are the real
// thing: the rule under test is what the screen does with a dial it did not choose.
vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  const actual = await vi.importActual<typeof import('../lib/device-mode')>('../lib/device-mode');
  const deviceMode = ref<'shared' | 'personal'>('shared');
  // hub#514: trust comes from the server now. The mock starts `false` (fail-closed) and the test
  // flips it via `seedTrustedDevice`, mirroring what `GET /api/device/mode` would say.
  const deviceTrusted = ref(false);
  return {
    deviceMode,
    deviceTrusted,
    deviceModeReady: ref(true),
    loadDeviceMode: vi.fn(async () => {
      return deviceMode.value;
    }),
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
import { STRICT_PIN_POLICY, pinPolicy } from '../lib/pin-policy';

// Read from the vitest root (`apps/web`): under happy-dom `import.meta.url` is not a `file:` URL.
const source = readFileSync(`${process.cwd()}/src/views/LoginPage.vue`, 'utf8');

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

/** The counter till as the hub sees it: one person enrolled, an online login already done here. */
function seedTrustedDevice(): void {
  localStorage.setItem('erplora.trusted', '1');
  localStorage.setItem(
    'erplora.trusted_users',
    JSON.stringify([{ id: 'u1', name: 'Marta Ruiz', email: 'marta@bar.example', initials: 'MR' }]),
  );
  pinUsers.value = [{ id: 'u1', name: 'Marta Ruiz', role: 'employee' }];
  hubContextReady.value = true;
  machineRegistrationRequired.value = false;
  // hub#514: trust comes from the server. The test simulates `GET /api/device/mode` answering
  // `trusted: true` for this device — what the old `erplora.trusted` flag pretended to be.
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

beforeEach(() => {
  localStorage.clear();
  deviceMode.value = 'shared';
  pinPolicy.value = STRICT_PIN_POLICY;
  vi.mocked(loadDeviceMode).mockClear();
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
});

describe('the shop that decided not to ask', () => {
  it('takes the pinpad away from a shared till when the dial says «never»', async () => {
    // The one-person minimarket. The device is genuinely shared (it is the counter till) and it has
    // signed in online, so hub#358 alone would paint the pinpad. The business said not to.
    seedTrustedDevice();
    pinPolicy.value = 'never';

    const wrapper = await mountLogin();

    expect(wrapper.find('ok-pinpad').exists()).toBe(false);
    // Not even the tab: an offer that only leads to four digits nobody will be asked for is noise.
    expect(wrapper.findComponent({ name: 'IonSegment' }).exists()).toBe(false);
    // What is left is the account route — stricter than four digits, never a way in that was not
    // there before. Turning the dial off gives up attribution, not the lock.
    expect(wrapper.find('form.step-form').exists()).toBe(true);
  });

  it('keeps the pinpad on the two positions that still ask', async () => {
    for (const policy of ['always', 'per_shift'] as const) {
      seedTrustedDevice();
      pinPolicy.value = policy;

      const wrapper = await mountLogin();

      expect(wrapper.find('ok-pinpad').exists(), policy).toBe(true);
      localStorage.clear();
    }
  });

  it('takes the pinpad away when the answer arrives after the screen is already up', async () => {
    // The hub answers over the network, so the pinpad is painted first and the dial lands later. A
    // screen that read the dial once would keep the pinpad it drew in the first frame until
    // somebody reloaded — and nobody reloads a login screen.
    seedTrustedDevice();
    const wrapper = await mountLogin();
    expect(wrapper.find('ok-pinpad').exists()).toBe(true);

    pinPolicy.value = 'never';
    await flushPromises();

    expect(wrapper.find('ok-pinpad').exists()).toBe(false);
  });

  it('keeps the PIN users the runtime reports — the dial hides the door, it does not forget them', async () => {
    // Turning the dial to «never» must not delete anybody's PIN: turning it back has to bring the
    // same pinpad back, with the same faces on it. Same rule as marking a device personal.
    seedTrustedDevice();
    pinPolicy.value = 'never';

    await mountLogin();

    expect(JSON.parse(localStorage.getItem('erplora.trusted_users') ?? '[]')).toHaveLength(1);
  });
});

describe('the lock cannot be removed from in front of the lock', () => {
  it('never writes the dial from the login screen', async () => {
    seedTrustedDevice();
    pinPolicy.value = 'never';

    await mountLogin();

    // Two doors, both closed to this screen: the hub's settings (`PUT /api/settings`, admin
    // session) and the shared value itself. Writing either from a screen that runs with no session
    // would be a lock with the key taped to it.
    expect(source).not.toContain('updateHubSettings');
    expect(source).not.toContain('publishPinPolicy');
    expect(source).not.toContain('setPinPolicy');
  });

  it('gates the pinpad on the shared decision, not on a local rule of its own', () => {
    // The whole decision lives in `offersPinLogin` (lib/device-mode.ts): shared AND device-trust
    // AND a dial that still asks. A second copy of that rule in the screen would drift, and the
    // half that drifts is always the half that stops checking.
    expect(source).toContain('offersPinLogin');
    expect(source).toContain('pinPolicy');
    expect(source).not.toMatch(/pinPolicy\.value\s*===?\s*'never'/);
  });

  it('does not send a device to the PIN setup step while the dial says never', async () => {
    // After the first cloud login the screen offers "choose your PIN". With the dial off that is a
    // dead end: four digits nobody would ever be asked for again.
    const setup = source.slice(source.indexOf('if (trust.value'), source.indexOf("step.value = 'setup'"));
    expect(setup).toContain('pinAvailable');
  });
});
