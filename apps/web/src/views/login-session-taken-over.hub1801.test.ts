// @vitest-environment happy-dom
// hub#1801 — **the screen that has to say it**, the last leg of the eviction chain.
//
// The plan covers one device. The till signs in, the laptop in the back office is displaced, and
// until now that laptop simply landed on the login with no word about it: the person had typed
// nothing, changed nothing and been told nothing, so the reading closest to hand is «the hub is
// down» or «somebody changed my password». That is a support call, and the hub had the answer all
// along.
//
// The runtime now names the reason (`session_evicted_device_limit`) and `main.ts` carries it here
// in the query. What this file pins is the three things that make the notice worth painting:
//
//  1. The reason is EXPLAINED, with the catalogue's own sentences — never a hardcoded line and
//     never the raw code, which is an English word with underscores to whoever runs the shop.
//  2. The way OUT is offered — the plan page of THIS hub in the account (hub#1685's recipe), and
//     never the marketplace (hub#479/#756). Gated by who shipped the binary: inside a Play copy
//     the store's rules forbid the door, so the notice stays and the button goes.
//  3. An ORDINARY expiry paints nothing. Telling that person they were thrown out — and inviting
//     them to pay for a bigger plan — would be a lie the screen made up on its own.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

import { SESSION_EVICTED_DEVICE_LIMIT } from '../lib/session-end-reason';

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

const { distribution, query, openExternal, saasDoor } = doubles;

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
  openExternal.mockClear();
  saasDoor.mockClear();
});

describe('the login screen explains the eviction (hub#1801)', () => {
  it('says what happened, in the words of the catalogue', async () => {
    query.value = { reason: SESSION_EVICTED_DEVICE_LIMIT };

    const notice = (await mountLogin()).find('[data-testid="login-session-ended"]');

    expect(notice.exists()).toBe(true);
    // The heading rides the ATTRIBUTE (`ok-inline-feedback` paints it inside its shadow root, which
    // a unit test never upgrades), the body rides the slot. Asserting the attribute is asserting
    // the real contract — and it still fails if the heading goes missing or is hardcoded.
    expect(notice.attributes('heading')).toBe(en.login.sessionTakenOver);
    expect(notice.text()).toContain(en.login.sessionTakenOverBody);
    // The code is a fact for the machine, not a sentence for a person.
    expect(notice.text()).not.toContain(SESSION_EVICTED_DEVICE_LIMIT);
    expect(notice.attributes('heading')).not.toContain(SESSION_EVICTED_DEVICE_LIMIT);
  });

  it('offers the way out: the plan page of this hub in the account, never the marketplace', async () => {
    query.value = { reason: SESSION_EVICTED_DEVICE_LIMIT };
    const wrapper = await mountLogin();

    const upgrade = wrapper.find('[data-testid="login-upgrade-plan"]');
    expect(upgrade.exists()).toBe(true);

    await upgrade.trigger('click');
    await flushPromises();

    expect(openExternal).toHaveBeenCalledTimes(1);
    const opened = String(openExternal.mock.calls[0]?.[0] ?? '');
    expect(opened).toContain('/change-plan/');
    expect(opened).not.toContain('/marketplace');
  });

  it('inside a Play copy the notice stays and the button goes (hub#756)', async () => {
    query.value = { reason: SESSION_EVICTED_DEVICE_LIMIT };
    distribution.value = 'play';

    const wrapper = await mountLogin();

    expect(wrapper.find('[data-testid="login-session-ended"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="login-upgrade-plan"]').exists()).toBe(false);
  });

  it('reads in Spanish too: every sentence of the notice has its `es` (ADR-0055/0199)', async () => {
    query.value = { reason: SESSION_EVICTED_DEVICE_LIMIT };
    i18n.global.locale.value = 'es';
    try {
      const notice = (await mountLogin()).find('[data-testid="login-session-ended"]');
      expect(notice.attributes('heading')).toBe(es.login.sessionTakenOver);
      expect(notice.text()).toContain(es.login.sessionTakenOverBody);
      expect(notice.text()).not.toContain(en.login.sessionTakenOverBody);
      // And the button too: a Spanish notice with an English way out is still a hardcoded string.
      expect(notice.text()).toContain(es.nav.upgradePlan);
    } finally {
      i18n.global.locale.value = 'en';
    }
  });
});

describe('what must NOT be painted', () => {
  it('an ordinary expiry gets no eviction notice and no invitation to pay', async () => {
    query.value = { reason: 'session-expired' };

    const wrapper = await mountLogin();

    expect(wrapper.find('[data-testid="login-session-ended"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="login-upgrade-plan"]').exists()).toBe(false);
  });

  it('a plain visit to the login is unchanged', async () => {
    const wrapper = await mountLogin();

    expect(wrapper.find('[data-testid="login-session-ended"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="login-box"]').exists()).toBe(true);
  });

  it('a reason nobody has a sentence for is not paraded on the screen', async () => {
    // Degrading is the rule (`lib/session-end-reason.ts`): a code from a later release has no
    // entry in the catalogue, and painting it raw would be worse than saying nothing.
    query.value = { reason: 'session_evicted_by_something_we_ship_next_year' };

    const wrapper = await mountLogin();

    expect(wrapper.find('[data-testid="login-session-ended"]').exists()).toBe(false);
  });
});
