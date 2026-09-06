// @vitest-environment happy-dom
// hub#1539 — «Mi perfil» → «Gestionar cuenta» is the fourth door out to erplora.com, and the only
// one that was still crossing with nothing.
//
// pm#196 gave the other three a ONE-TIME pass, because inside the installed app the link opens in
// the system browser, whose cookie jar is not the webview's: the person had signed in minutes ago
// and still landed on a login form — password and second factor again. This one was left out on
// purpose, because the pass was only minted for whoever administers the hub, and the account page
// is not administration: an assistant manager who typed her email and her password has every right
// to change her own password. The runtime now tells the two apart (`is_own_account_destination`),
// so this door can cross like the rest.
//
// The pass is asked for only when it CAN be minted — the session was opened with an email and a
// password. A PIN session is refused by design (hub#1400), and asking anyway would mean a reported
// failure every single time somebody on a shift pressed the button: noise that teaches everyone to
// ignore the report, for a link that was going to open either way.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import es from '../i18n/locales/es';

vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));

const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/open-external', () => ({ openExternal }));

const { saasDoor } = vi.hoisted(() => ({
  saasDoor: vi.fn(async () => 'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2Fprofile%2F'),
}));
vi.mock('../lib/saas-door', () => ({ saasDoor }));

import ProfilePage from './ProfilePage.vue';
import { config } from '../lib/config';
import { setHubSession } from '../lib/session';
import { resetUserProfile } from '../lib/user-profile';

const PLAIN = `${config.cloudApiUrl.replace(/\/+$/, '')}/dashboard/profile/`;

function stubRuntime(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(
        JSON.stringify({
          id: 'u-1',
          name: 'Nora Vega',
          first_name: 'Nora',
          last_name: 'Vega',
          email: 'nora@example.com',
          role: 'employee',
          permissions: [],
          cloud_user_id: '77',
          avatar_url: null,
          has_pin: true,
          preferences: { language: null, theme_mode: null, theme_palette: null },
        }),
        { status: 200 },
      ),
    ),
  );
}

async function pressManageAccount(): Promise<void> {
  const i18n = createI18n({ legacy: false, locale: 'es', fallbackLocale: 'es', messages: { es } });
  const wrapper = mount(ProfilePage, {
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  }) as unknown as { vm: { manageCloudAccount: () => Promise<void> } };
  await flushPromises();
  await wrapper.vm.manageCloudAccount();
  await flushPromises();
}

beforeEach(() => {
  resetUserProfile();
  localStorage.clear();
  openExternal.mockClear();
  saasDoor.mockClear();
  saasDoor.mockResolvedValue(
    'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2Fprofile%2F',
  );
  stubRuntime();
});

afterEach(() => {
  setHubSession(null);
  vi.restoreAllMocks();
});

describe('«Mi perfil» → the account at erplora.com (hub#1539)', () => {
  it('crosses with the one-time pass when the session was opened with a password', async () => {
    setHubSession('sess-1', 'cloud');

    await pressManageAccount();

    expect(openExternal).toHaveBeenCalledWith(
      'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2Fprofile%2F',
    );
  });

  it('asks the runtime with the PATH, so the address is built where the SaaS is known', async () => {
    // A page that could choose the host would be choosing where the pass gets spent, and the pass
    // opens a session.
    setHubSession('sess-1', 'cloud');

    await pressManageAccount();

    expect(saasDoor).toHaveBeenCalledWith('/dashboard/profile/', PLAIN, 'cloud-account');
  });

  it('still opens the plain link when the pass cannot be minted', async () => {
    // Degrading is the contract, not a bug: the person arrives the way she did before pm#196.
    setHubSession('sess-1', 'cloud');
    saasDoor.mockResolvedValue(PLAIN);

    await pressManageAccount();

    expect(openExternal).toHaveBeenCalledWith(PLAIN);
  });

  it('does not even ask for a pass on a shift session, and opens the link all the same', async () => {
    // hub#1400: a four-digit code typed in front of people never carries off a browser session.
    setHubSession('sess-1', 'pin');

    await pressManageAccount();

    expect(saasDoor).not.toHaveBeenCalled();
    expect(openExternal).toHaveBeenCalledWith(PLAIN);
  });
});
