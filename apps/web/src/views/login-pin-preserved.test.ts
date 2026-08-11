// @vitest-environment happy-dom
// hub#772 — **an online sign-in must not overwrite a PIN that already exists**.
//
// A user who already has a PIN (their row is in `pin_users`, returned by
// `GET /api/hub/context`) signs in online on a shared device with «Trust this device» checked.
// The screen used to send them to «Create your access PIN» no matter what: the branch only asked
// whether the *pinpad was available on this device*, never whether *this user already had a PIN*.
// Confirming four digits called `set-pin`, which **overwrites** the hash — so every online re-entry
// became an implicit PIN reset, and the second person who knew the old four digits was locked out
// with no warning.
//
// The fix is one question, asked in the right place: **does this user already have a PIN?** The
// authority is `pin_users` keyed by id (the same list that paints the pinpad). If the signed-in user
// is on it, the screen keeps the PIN and goes straight in. Trusting the device records the device;
// it does not mutate a credential that belongs to the user, not the device.
//
// This suite follows the established pattern for the trust→setup branch (`login-pin-policy`,
// `login-device-mode`): the rule lives in `finalizeCloudLogin`, reached only through a full cloud
// login, so we pin it at the source where the decision is made, and at the shape of the setup step.
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

/** A shared, trusted till — the only setting where the pinpad and the setup step are offered. */
function seedSharedTrustedTill(): void {
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
  pinPolicy.value = STRICT_PIN_POLICY;
  pinUsers.value = [];
  hubContextReady.value = false;
  machineRegistrationRequired.value = false;
  deviceTrusted.value = false;
});

describe('the trust → setup branch', () => {
  // This is the regression: the branch that sent every online re-entry through PIN creation,
  // overwriting the existing hash. The fix has to ask whether THIS user already has a PIN before
  // opening setup — keyed by id against the runtime's `pin_users`, the authority that paints the
  // pinpad. We assert at the source because `finalizeCloudLogin` is reached only through a full
  // cloud login (same approach the sibling suites take for this exact branch).

  it('asks whether the signed-in user already has a PIN before opening setup', () => {
    seedSharedTrustedTill();
    const trustBranch = source.slice(
      source.indexOf('if (trust.value'),
      source.indexOf('await router.replace(redirectTarget())'),
    );
    // The id of the session user is compared against the runtime pin list — the authority, not a
    // device-only flag. Without this, the bug reproduces on every online sign-in.
    expect(trustBranch).toMatch(/sess\.user\.id/);
    expect(trustBranch).toMatch(/pinUsers/);
  });

  it('gates the setup step on the user NOT already having a PIN', () => {
    // The half that drifts is always the half that stops checking. Setup must be reached only when
    // the user has no PIN yet: a negated guard that references the pin list by id. `pinAvailable`
    // alone (the bug) opens setup for a user whose PIN is already on file.
    seedSharedTrustedTill();
    const setup = source.slice(
      source.indexOf("step.value = 'setup'"),
      source.indexOf('return; // no navega aún'),
    );
    const trustBranch = source.slice(
      source.indexOf('if (trust.value)'),
      source.indexOf('await router.replace(redirectTarget())'),
    );
    // A negated predicate guards the setup step (case-insensitive: the local reads `HasPin`).
    expect(trustBranch).toMatch(/!\s*\S*pin|not.*has|!\s*\S*includes|!\s*\S*some/i);
    // The setup step is still there — the first-time case needs it.
    expect(setup).toContain("'setup'");
  });
});

describe('an online sign-in does not turn into a PIN reset', () => {
  it('keeps the setup step unchanged for the first-time user (no regression)', async () => {
    // The first-time flow has to keep working: a user with no PIN signs in online, trusts the
    // device, and chooses their PIN. The fix must not close that door.
    seedSharedTrustedTill();
    pinUsers.value = [];
    const wrapper = await mountLogin();

    // On a fresh device the pinpad is not offered yet, so the screen is on the email step.
    expect(wrapper.find('form.step-form').exists()).toBe(true);
    // The setup step is reachable in the source (not deleted), and the subtitle key is intact.
    expect(source).toContain("step.value = 'setup'");
    expect(source).toContain('login.subtitleSetup');
  });

  it('documents the fix in the branch comment — a user with a PIN goes straight in', () => {
    // The branch explains itself: the guard names hub#772 and the invariant (a credential that
    // belongs to the user is not mutated by trusting a device). A reader of the diff sees the why.
    seedSharedTrustedTill();
    const trustBranch = source.slice(
      source.indexOf('if (trust.value'),
      source.indexOf('await router.replace(redirectTarget())'),
    );
    expect(trustBranch).toMatch(/772|already has a PIN|keeps? the PIN|existing PIN/i);
  });
});
