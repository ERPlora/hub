// «My profile» (`/profile`, BASE-G125 and G126; the old hub's ProfilePage): the person's name, contact email and photo,
// their language and appearance (applied at once, saved for them on every device) and their own PIN. The summary is
// named in the person's language (gh:hub#2589). A profile that cannot be read offers nothing to save, only «Retry».
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import { onSessionChanged } from '../lib/access';
import type { Profile } from '../operations';
import ProfilePage from './ProfilePage.vue';

const shell = vi.hoisted(() => ({ applyUserThemePreferences: vi.fn(), resetUserThemePreferences: vi.fn() }));
vi.mock('@erplora/ui/shell', async (original) => ({ ...(await original<typeof import('@erplora/ui/shell')>()), ...shell }));

const PROFILE: Profile = {
  first_name: 'Ana',
  last_name: 'López',
  contact_email: 'ana@bar.example',
  avatar_url: '',
  language: '',
  theme_mode: '',
  palette: '',
  role: 'hub_owner',
  has_pin: true,
  pin_length: 4,
};

type Answer = (url: string, body: Record<string, unknown> | undefined) => Response;
const ok: Answer = (url, body) => {
  if (url.startsWith('/api/me/profile/update')) return Response.json({ ...PROFILE, ...body });
  if (url.startsWith('/api/me/preferences')) return Response.json({ ...body, language: body?.language || 'es' });
  if (url.startsWith('/api/me/pin')) return Response.json({ set: true });
  if (url.startsWith('/api/me/avatar/remove')) return Response.json({ avatar_url: '' });
  if (url.startsWith('/api/me/avatar')) return Response.json({ avatar_url: '/media/avatars/a.png' });
  return Response.json({});
};

async function profile(data: Profile | null = PROFILE, answer: Answer = ok, locale: 'en' | 'es' = 'en') {
  const mounted = await mountBase(ProfilePage, {
    path: '/profile',
    routes: ['/profile'],
    locale,
    onApi: ({ url, init }) => answer(url, init.body ? JSON.parse(String(init.body)) : undefined),
  });
  const call = await mounted.live();
  if (data) await mounted.result(call, 'base.profile.get', data);
  const calls = (path: string) =>
    mounted.net.api.filter((c) => c.url.startsWith(path)).map((c) => (c.init.body ? JSON.parse(String(c.init.body)) : undefined));
  const type = async (testid: string, value: string) => {
    const field = mounted.wrapper.get(`[data-testid="${testid}"]`);
    (field.element as HTMLInputElement & { value: string }).value = value;
    field.element.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  };
  return { ...mounted, call, calls, type };
}

beforeEach(() => {
  shell.applyUserThemePreferences.mockReset();
  shell.resetUserThemePreferences.mockReset();
});
afterEach(() => {
  document.body.innerHTML = '';
});

describe('ProfilePage — who I am', () => {
  it('heads with the person, their role and the account summary’s name', async () => {
    const { wrapper } = await profile();
    const summary = wrapper.get('[data-testid="profile-summary"]');
    expect(summary.attributes('aria-label')).toBe('Account summary');
    expect(summary.text()).toContain('Ana López');
    expect(summary.text()).toContain('Owner');
  });

  it('«Save my details» saves the name and the contact email', async () => {
    const { wrapper, calls, type } = await profile();
    await type('profile-first-name', 'Ana María');
    await type('profile-email', 'ana.maria@bar.example');
    await wrapper.get('[data-testid="profile-save"]').trigger('click');
    await flush();
    expect(calls('/api/me/profile/update')).toEqual([
      { first_name: 'Ana María', last_name: 'López', contact_email: 'ana.maria@bar.example' },
    ]);
    expect(wrapper.get('[data-testid="profile-saved"]').text()).toBe('Profile saved');
  });

  it('a saved name tells the shell its session changed, so the side menu takes it without a reload', async () => {
    const changed = vi.fn();
    const stop = onSessionChanged(changed);
    try {
      const { wrapper, type } = await profile();
      await type('profile-first-name', 'Ana María');
      await wrapper.get('[data-testid="profile-save"]').trigger('click');
      await flush();
      expect(changed).toHaveBeenCalledOnce();
    } finally {
      stop();
    }
  });

  it('a refused save says so, with the Hub’s reason, and keeps what was typed', async () => {
    const refuse: Answer = (url, body) =>
      url.startsWith('/api/me/profile/update')
        ? Response.json({ error: { code: 'invalid_payload', message: 'Enter a valid contact email.' } }, { status: 422 })
        : ok(url, body);
    const changed = vi.fn();
    const stop = onSessionChanged(changed);
    const { wrapper, type } = await profile(PROFILE, refuse);
    await type('profile-email', 'not-an-email');
    await wrapper.get('[data-testid="profile-save"]').trigger('click');
    await flush();
    const error = wrapper.get('[data-testid="profile-save-error"]');
    expect(changed).not.toHaveBeenCalled();
    expect(error.text()).toContain('Could not save the profile');
    expect(error.text()).toContain('Enter a valid contact email.');
    expect((wrapper.get('[data-testid="profile-email"]').element as HTMLInputElement & { value: string }).value).toBe(
      'not-an-email',
    );
    stop();
  });

  it('a profile that cannot be read offers only «Retry», nothing to save', async () => {
    const { wrapper, call, client } = await profile(null);
    call.push(errorFrame(subId(client, 'base.profile.get'), 'unexpected'));
    await flush();
    expect(wrapper.get('[data-testid="profile-load-error"]').text()).toContain('Could not load the profile');
    expect(wrapper.find('[data-testid="profile-retry"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="profile-save"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="profile-pin"]').exists()).toBe(false);
  });

  it('while it is read, it says so', async () => {
    const { wrapper } = await profile(null);
    expect(wrapper.get('[data-testid="profile-loading"]').text()).toBe('Loading your profile…');
  });
});

describe('ProfilePage — preferences', () => {
  it('a language is saved for the person and applied at once', async () => {
    const { wrapper, calls } = await profile();
    const select = wrapper.get('[data-testid="profile-language"]');
    select.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'es' } }));
    await flush();
    expect(calls('/api/me/preferences')).toEqual([{ language: 'es', theme_mode: '', palette: '' }]);
    expect(wrapper.vm.$i18n.locale).toBe('es');
  });

  it('a mode and a palette are saved and painted', async () => {
    const { wrapper, calls } = await profile();
    wrapper.get('[data-testid="profile-mode"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'dark' } }));
    await flush();
    await wrapper.get('[data-testid="profile-palette-forest"]').trigger('click');
    await flush();
    expect(calls('/api/me/preferences')).toEqual([
      { language: '', theme_mode: 'dark', palette: '' },
      { language: '', theme_mode: 'dark', palette: 'forest' },
    ]);
    expect(shell.applyUserThemePreferences).toHaveBeenLastCalledWith('dark', 'forest');
  });

  it('«Use the business’s appearance» undoes the person’s own', async () => {
    const { wrapper, calls } = await profile({ ...PROFILE, theme_mode: 'dark', palette: 'forest' });
    await wrapper.get('[data-testid="profile-appearance-business"]').trigger('click');
    await flush();
    expect(calls('/api/me/preferences')).toEqual([{ language: '', theme_mode: '', palette: '' }]);
    expect(shell.resetUserThemePreferences).toHaveBeenCalled();
  });
});

describe('ProfilePage — my PIN', () => {
  it('with a PIN: the current one, the new one twice, «Change PIN»', async () => {
    const { wrapper, calls, type } = await profile();
    expect(wrapper.get('[data-testid="profile-pin"]').text()).toContain('The PIN you enter the till with.');
    await type('profile-pin-current', '4826');
    await type('profile-pin-new', '9071');
    await type('profile-pin-repeat', '9071');
    await wrapper.get('[data-testid="profile-pin-save"]').trigger('click');
    await flush();
    expect(calls('/api/me/pin')).toEqual([{ pin: '9071', current: '4826' }]);
    expect(wrapper.get('[data-testid="profile-pin-saved"]').text()).toBe('PIN updated');
  });

  it('without one: «Set PIN», no current PIN asked', async () => {
    const { wrapper, calls, type } = await profile({ ...PROFILE, has_pin: false });
    expect(wrapper.text()).toContain('You do not have a PIN yet.');
    expect(wrapper.find('[data-testid="profile-pin-current"]').exists()).toBe(false);
    await type('profile-pin-new', '9071');
    await type('profile-pin-repeat', '9071');
    expect(wrapper.get('[data-testid="profile-pin-save"]').text()).toBe('Set PIN');
    await wrapper.get('[data-testid="profile-pin-save"]').trigger('click');
    await flush();
    expect(calls('/api/me/pin')).toEqual([{ pin: '9071' }]);
  });

  it.each([
    ['907', '907', 'The PIN must have 4 digits.'],
    ['9071', '9072', 'The two PINs do not match.'],
  ])('%s and %s: «%s», and nothing is sent', async (fresh, repeat, message) => {
    const { wrapper, calls, type } = await profile({ ...PROFILE, has_pin: false });
    await type('profile-pin-new', fresh);
    await type('profile-pin-repeat', repeat);
    await wrapper.get('[data-testid="profile-pin-save"]').trigger('click');
    await flush();
    expect(calls('/api/me/pin')).toEqual([]);
    expect(wrapper.get('[data-testid="profile-pin-error"]').text()).toBe(message);
  });

  it('the Hub’s refusal (wrong current PIN, taken, too easy) is its sentence', async () => {
    const refuse: Answer = (url, body) =>
      url.startsWith('/api/me/pin')
        ? Response.json(
            { error: { code: 'base.pin_current_wrong', message: 'That is not your current PIN. Type it right to set a new one.' } },
            { status: 403 },
          )
        : ok(url, body);
    const { wrapper, type } = await profile(PROFILE, refuse);
    await type('profile-pin-current', '0000');
    await type('profile-pin-new', '9071');
    await type('profile-pin-repeat', '9071');
    await wrapper.get('[data-testid="profile-pin-save"]').trigger('click');
    await flush();
    expect(wrapper.get('[data-testid="profile-pin-error"]').text()).toBe(
      'That is not your current PIN. Type it right to set a new one.',
    );
  });
});

describe('ProfilePage — Spanish', () => {
  it('names the summary and the cards in Spanish (gh:hub#2589)', async () => {
    const { wrapper } = await profile(PROFILE, ok, 'es');
    expect(wrapper.get('[data-testid="profile-summary"]').attributes('aria-label')).toBe('Resumen de la cuenta');
    expect(wrapper.text()).toContain('Datos de la cuenta');
    expect(wrapper.text()).toContain('Preferencias');
    expect(wrapper.text()).toContain('Propietario');
  });

  it('names each palette in Spanish, never by its English id (BASE-G152)', async () => {
    const { wrapper } = await profile(PROFILE, ok, 'es');
    const names = wrapper.findAll('.profile__palette-name').map((name) => name.text());
    expect(names).toEqual(['ERPlora', 'Terracota', 'Corporativo', 'Minimalista', 'Bosque', 'Océano', 'Violeta']);
  });

  it('and in English', async () => {
    const { wrapper } = await profile(PROFILE, ok, 'en');
    const names = wrapper.findAll('.profile__palette-name').map((name) => name.text());
    expect(names).toEqual(['ERPlora', 'Terracotta', 'Corporate', 'Minimal', 'Forest', 'Ocean', 'Violet']);
  });
});
