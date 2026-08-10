// @vitest-environment happy-dom
// hub#358 — **the pinpad belongs to the device, not to the hub**.
//
// One business has the till at the counter, where four people take turns, and the owner's own
// laptop in the back office — and the same person uses both. The till has to ask who is standing
// at it; the laptop asking its owner for four digits every morning is friction that buys nothing.
// So the login screen stops deciding from what it finds in `localStorage` and asks the hub what
// kind of device this is (`GET /api/device/mode`, hub#357).
//
// The bug these tests describe, in one line: **the login screen used to paint the pinpad on any
// device that had ever signed in online**, and there was no way to tell it otherwise.
//
// Two invariants matter more than the layout:
//
//   1. **The screen READS the mode and never writes it.** It runs before any session exists. If it
//      could set the mode, the lock could be removed without passing through the lock — a login
//      screen that turns its own pinpad off is not a lock at all.
//   2. **Not knowing means the pinpad.** The mode client already fails closed
//      (`lib/device-mode.test.ts`); here it must not be second-guessed with a local default.
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
import { deviceMode, deviceTrusted, loadDeviceMode, setDeviceMode } from '../lib/device-mode';

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
  vi.mocked(loadDeviceMode).mockClear();
  vi.mocked(setDeviceMode).mockClear();
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
});

describe('the counter till', () => {
  it('shows the pinpad, because several people take turns at it', async () => {
    seedTrustedDevice();

    const wrapper = await mountLogin();

    expect(wrapper.find('ok-pinpad').exists()).toBe(true);
    expect(wrapper.findComponent({ name: 'IonSegment' }).exists()).toBe(true);
  });

  it('asks the hub which device this is, instead of reading it off this browser', async () => {
    seedTrustedDevice();

    await mountLogin();

    expect(vi.mocked(loadDeviceMode)).toHaveBeenCalled();
  });
});

describe("somebody's own device", () => {
  it('does not show the pinpad: it signs in with the account', async () => {
    seedTrustedDevice();
    deviceMode.value = 'personal';

    const wrapper = await mountLogin();

    expect(wrapper.find('ok-pinpad').exists()).toBe(false);
    // Not even the tab: an offer that only leads to four digits nobody wants to type is noise.
    expect(wrapper.findComponent({ name: 'IonSegment' }).exists()).toBe(false);
    // What it shows instead: the account form, and a line saying what "personal" costs — it stays
    // signed in. Silence there is what makes a lost device a surprise.
    expect(wrapper.find('form.step-form').exists()).toBe(true);
    expect(wrapper.html()).toContain('login.personalDeviceNote');
    // And no "trust this device" box: on a device an administrator already called personal, a
    // checkbox that changes nothing is a lie with a tick in it.
    expect(wrapper.html()).not.toContain('login.trustDevice');
  });

  it('takes the pinpad away when the answer arrives after the screen is already up', async () => {
    // The hub answers over the network, so the pinpad is painted first and the answer lands later.
    // If the screen only looked at the mode once, a personal laptop would keep the pinpad it drew
    // in the first frame until somebody reloaded — and nobody reloads a login screen.
    seedTrustedDevice();
    const wrapper = await mountLogin();
    expect(wrapper.find('ok-pinpad').exists()).toBe(true);

    deviceMode.value = 'personal';
    await flushPromises();

    expect(wrapper.find('ok-pinpad').exists()).toBe(false);
  });

  it('keeps the PIN users the runtime reports — the mode hides the door, it does not forget them', async () => {
    // Turning the laptop personal must not delete anybody's PIN: putting the device back behind
    // the counter has to bring the same pinpad back, with the same faces on it.
    seedTrustedDevice();
    deviceMode.value = 'personal';

    await mountLogin();

    expect(JSON.parse(localStorage.getItem('erplora.trusted_users') ?? '[]')).toHaveLength(1);
  });
});

describe('the lock cannot be removed from in front of the lock', () => {
  it('never writes the mode from the login screen', async () => {
    seedTrustedDevice();

    await mountLogin();

    // The screen runs with no session at all. A screen that could turn its own pinpad off would
    // be a lock with the key taped to it; the write door takes an ADMIN session for that reason.
    expect(vi.mocked(setDeviceMode)).not.toHaveBeenCalled();
    expect(source).not.toContain('setDeviceMode');
  });

  it('gates the pinpad on the shared decision, not on a local flag of its own', () => {
    // The single decision lives in `offersPinLogin` (lib/device-mode.ts), where both halves are
    // required: shared AND device-trust. A second copy of that rule here would drift.
    expect(source).toContain('offersPinLogin');
    expect(source).toContain('loadDeviceMode');
  });

  it('does not send a device to the PIN setup step when it has no pinpad', () => {
    // After the first cloud login the screen offers "choose your PIN". On a personal device that
    // is a dead end: the PIN it stores would never be asked for again.
    const setup = source.slice(source.indexOf('if (trust.value'), source.indexOf("step.value = 'setup'"));
    expect(setup).toContain('pinAvailable');
  });
});
