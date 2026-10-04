// @vitest-environment happy-dom
// hub#2451 — «Mi perfil» → «Borrar mi cuenta». Google Play demands that an app which lets people
// sign up also lets them delete that account from inside the app, and that the option is easy to
// find (a link to a web page is allowed). The deletion already lived at erplora.com, one page past
// «Manage account at erplora.com» — reachable, but nobody looking for «delete» would guess it. The
// button opens the SaaS's deletion confirmation directly, on the account surface (no panel, hub#1900)
// and through the same one-time pass as the account door (hub#1539), so the person does not type her
// password again in the system browser.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const { toast } = vi.hoisted(() => ({ toast: vi.fn(async () => {}) }));
vi.mock('../lib/toast', () => ({ toast }));

const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/open-external', () => ({ openExternal }));

const PASS = 'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2Fprofile%2Fdelete%2F';
const { saasDoor } = vi.hoisted(() => ({ saasDoor: vi.fn(async () => '') }));
vi.mock('../lib/saas-door', () => ({ saasDoor }));

import ProfilePage from './ProfilePage.vue';
import { config } from '../lib/config';
import { setHubSession } from '../lib/session';
import { resetUserProfile } from '../lib/user-profile';

const DELETION = '/dashboard/profile/delete/?surface=account';
const PLAIN = `${config.cloudApiUrl.replace(/\/+$/, '')}${DELETION}`;
const BUTTON = '[data-testid="profile-delete-account"]';

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

async function render() {
  const i18n = createI18n({ legacy: false, locale: 'es', fallbackLocale: 'es', messages: { es } });
  const wrapper = mount(ProfilePage, { global: { plugins: [i18n], renderStubDefaultSlot: true } });
  await flushPromises();
  return wrapper;
}

async function pressDelete(): Promise<void> {
  const wrapper = await render();
  await wrapper.find(BUTTON).trigger('click');
  await flushPromises();
}

beforeEach(() => {
  resetUserProfile();
  localStorage.clear();
  openExternal.mockClear();
  openExternal.mockResolvedValue(undefined);
  saasDoor.mockClear();
  saasDoor.mockResolvedValue(PASS);
  toast.mockClear();
  stubRuntime();
});

afterEach(() => {
  setHubSession(null);
  vi.restoreAllMocks();
});

describe('«Mi perfil» → «Borrar mi cuenta» (hub#2451)', () => {
  it('is offered to whoever has an erplora.com account', async () => {
    localStorage.setItem('erplora.access', 'jwt-77');

    const wrapper = await render();

    expect(wrapper.find(BUTTON).exists()).toBe(true);
  });

  it('is not offered to a local identity, which has no erplora.com account to delete', async () => {
    const wrapper = await render();

    expect(wrapper.find(BUTTON).exists()).toBe(false);
  });

  it('opens the deletion confirmation with the one-time pass when the session was opened with a password', async () => {
    localStorage.setItem('erplora.access', 'jwt-77');
    setHubSession('sess-1', 'cloud');

    await pressDelete();

    expect(saasDoor).toHaveBeenCalledWith(DELETION, PLAIN, 'cloud-account-delete');
    expect(openExternal).toHaveBeenCalledWith(PASS);
  });

  it('opens the plain link on a shift session, without asking for a pass', async () => {
    // hub#1400: a PIN never carries off a browser session; the person signs in at erplora.com.
    localStorage.setItem('erplora.access', 'jwt-77');
    setHubSession('sess-1', 'pin');

    await pressDelete();

    expect(saasDoor).not.toHaveBeenCalled();
    expect(openExternal).toHaveBeenCalledWith(PLAIN);
  });

  it('says so when the browser could not be opened, instead of doing nothing', async () => {
    localStorage.setItem('erplora.access', 'jwt-77');
    setHubSession('sess-1', 'cloud');
    openExternal.mockRejectedValueOnce(new Error('no browser'));

    await pressDelete();

    expect(toast).toHaveBeenCalledWith(es.profile.cloudAccountError, 'danger');
  });

  it('has its label in English and Spanish', () => {
    expect(en.profile.deleteAccount).toBeTruthy();
    expect(es.profile.deleteAccount).toBeTruthy();
  });
});
