// @vitest-environment happy-dom
// **My profile that could not be read offers nothing to save** (hub#2541).
//
// `GET /api/profile` failing left the form EMPTY with «Save my details» live: pressing it sent empty
// first name, last name and e-mail and wiped them. The PIN card guessed «no PIN yet» from the
// missing profile. Now a failed read says so with Retry, and the details, preferences and PIN cards
// are not on screen until it works; the header (from the session) and account management stay.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import en from '../i18n/locales/en';

vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /></div>' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('../lib/toast', () => ({ toast: vi.fn() }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn() }));

import ProfilePage from './ProfilePage.vue';
import { setHubSession } from '../lib/session';
import { resetUserProfile } from '../lib/user-profile';

const PROFILE = {
  id: 'u-1',
  name: 'Nora Vega',
  first_name: 'Nora',
  last_name: 'Vega',
  email: 'nora@example.com',
  role: 'employee',
  permissions: [],
  cloud_user_id: null,
  avatar_url: null,
  has_pin: true,
  preferences: { language: null, theme_mode: null, theme_palette: null },
};

/**
 * `GET /api/profile` answers with what `readAnswers` hands out, one per read; writes to the profile
 * (`/api/profile`, its avatar and the PIN door) are recorded. The media handshake is not one.
 */
function stubRuntime(readAnswers: Array<() => Response>) {
  const writes: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      const method = init?.method ?? 'GET';
      if (method !== 'GET' && /\/api\/(profile|auth\/set-pin)/.test(path)) writes.push(`${method} ${path}`);
      if (path.endsWith('/api/profile') && method === 'GET') {
        const next = readAnswers.shift();
        return next ? next() : new Response(JSON.stringify(PROFILE), { status: 200 });
      }
      return new Response('{}', { status: 200 });
    }),
  );
  return writes;
}

const down = () => new Response(JSON.stringify({ ok: false, error: { code: 'service_unavailable' } }), { status: 503 });
const up = () => new Response(JSON.stringify(PROFILE), { status: 200 });

async function mountProfile() {
  const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en } });
  const wrapper = mount(ProfilePage, { global: { plugins: [i18n], renderStubDefaultSlot: true } });
  await flushPromises();
  return wrapper;
}

const has = (w: Awaited<ReturnType<typeof mountProfile>>, id: string) => w.find(`[data-testid="${id}"]`).exists();
const SAVING = [
  'profile-change-photo',
  'profile-first-name',
  'profile-save',
  'profile-language',
  'profile-theme',
  'profile-pin-form',
  'profile-save-pin',
];

beforeEach(() => {
  vi.unstubAllGlobals();
  setHubSession('sess-1');
  resetUserProfile();
});

afterEach(() => {
  setHubSession(null);
  resetUserProfile();
});

describe('My profile with the read down (hub#2541)', () => {
  it('🔴 says it could not load, with Retry, and offers nothing that saves', async () => {
    const writes = stubRuntime([down]);
    const wrapper = await mountProfile();

    expect(has(wrapper, 'profile-load-error')).toBe(true);
    expect(has(wrapper, 'profile-load-retry')).toBe(true);
    for (const id of SAVING) expect(has(wrapper, id), id).toBe(false);
    expect(writes, 'nothing was written').toEqual([]);
  });

  it('🔴 Retry reads again and, once it works, the form is back filled in', async () => {
    stubRuntime([down, up]);
    const wrapper = await mountProfile();

    await wrapper.find('[data-testid="profile-load-retry"]').trigger('click');
    await flushPromises();

    expect(has(wrapper, 'profile-load-error')).toBe(false);
    for (const id of SAVING) expect(has(wrapper, id), id).toBe(true);
    const vm = wrapper.vm as unknown as { firstName: string; email: string };
    expect(vm.firstName).toBe('Nora');
    expect(vm.email).toBe('nora@example.com');
  });

  it('Retry is off while it reads again, and back on if that read fails too', async () => {
    let answerRetry: (r: Response) => void = () => undefined;
    const answers: Array<() => Promise<Response>> = [
      async () => down(),
      () => new Promise<Response>((resolve) => (answerRetry = resolve)),
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request, init?: RequestInit) =>
        String(url).endsWith('/api/profile') && (init?.method ?? 'GET') === 'GET'
          ? answers.shift()!()
          : new Response('{}', { status: 200 }),
      ),
    );
    const wrapper = await mountProfile();
    // The real <ion-button> takes `disabled` as a property, not as an attribute.
    const retryOff = () =>
      (wrapper.find('[data-testid="profile-load-retry"]').element as HTMLElement & { disabled?: boolean }).disabled;
    expect(retryOff(), 'on before pressing').toBe(false);

    await wrapper.find('[data-testid="profile-load-retry"]').trigger('click');
    await flushPromises();
    expect(retryOff(), 'off while reading').toBe(true);

    answerRetry(down());
    await flushPromises();
    expect(has(wrapper, 'profile-load-error')).toBe(true);
    expect(retryOff(), 'on again after the failed read').toBe(false);
  });

  it('🔴 while the read is on its way it says it is loading, with no empty form', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => undefined)),
    );
    const wrapper = mount(ProfilePage, {
      global: {
        plugins: [
          createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en } }),
        ],
        renderStubDefaultSlot: true,
      },
    });
    await flushPromises();

    expect(has(wrapper, 'profile-loading')).toBe(true);
    expect(has(wrapper, 'profile-save')).toBe(false);
    expect(has(wrapper, 'profile-load-error')).toBe(false);
  });
});
