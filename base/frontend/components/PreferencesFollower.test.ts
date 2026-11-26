// The person's own preferences followed on every screen: base keeps the live `base.profile.get` open once per person
// and, when the language kept in «My profile» changes (the assistant's card, another tab), reads the session again,
// whose language the shell follows, so the open app speaks it without a reload; an appearance chosen anew there is
// painted at once, as «My profile» paints it. It paints nothing of its own.
import { resetUserThemePreferences, type SessionMe, themeMode, themePalette, themeScale } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { openFollower } from '../__tests__/followers';
import { OWNER } from '../__tests__/mount-base';
import { sessionChanged } from '../lib/access';
import type { Profile, ProfileLanguage } from '../operations/profile';
import PreferencesFollower from './PreferencesFollower.vue';

vi.mock('../lib/access', async (importOriginal) => (await import('../__tests__/apps-page-spies')).accessWithSessionSpy(importOriginal));

const me = ref<SessionMe>(OWNER);

function profile(language: ProfileLanguage, change: Partial<Profile> = {}): Profile {
  return {
    first_name: 'Ana',
    last_name: '',
    contact_email: '',
    avatar_url: '',
    language,
    theme_mode: '',
    palette: '',
    ui_scale: 100,
    role: 'hub_owner',
    has_pin: false,
    pin_length: 4,
    ...change,
  };
}

const open = () => openFollower(PreferencesFollower, { session: me, path: '/', screens: [] });

const dark = () => document.documentElement.classList.contains('ion-palette-dark');
let systemDark = false;

beforeEach(() => {
  vi.mocked(sessionChanged).mockClear();
  systemDark = false;
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('dark') && systemDark,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
  resetUserThemePreferences();
});
afterEach(() => {
  document.body.innerHTML = '';
  resetUserThemePreferences();
  vi.unstubAllGlobals();
});

describe('PreferencesFollower', () => {
  it('follows the person’s profile live and paints nothing', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.profile.get').map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.text()).toBe('');
  });

  it('the first answer reads nothing again; a language chosen anew does, once each time', async () => {
    const m = await open();
    await m.result(m.call, 'base.profile.get', profile(''));
    expect(sessionChanged).not.toHaveBeenCalled();

    await m.result(m.call, 'base.profile.get', profile('en'), 2);
    expect(sessionChanged).toHaveBeenCalledTimes(1);

    await m.result(m.call, 'base.profile.get', profile('es'), 3);
    expect(sessionChanged).toHaveBeenCalledTimes(2);

    // Back to the business's language: the session says which one that is.
    await m.result(m.call, 'base.profile.get', profile(''), 4);
    expect(sessionChanged).toHaveBeenCalledTimes(3);
  });

  it('a language chosen before the first answer came (the page still loading) and not the session’s reads it again', async () => {
    const m = await open();
    await m.result(m.call, 'base.profile.get', profile('es'));
    expect(sessionChanged).toHaveBeenCalledTimes(1);
  });

  it('a first answer the session already speaks, or the business’s language, reads nothing again', async () => {
    for (const language of ['en', ''] as const) {
      vi.mocked(sessionChanged).mockClear();
      const m = await open();
      await m.result(m.call, 'base.profile.get', profile(language));
      expect(sessionChanged).not.toHaveBeenCalled();
      m.wrapper.unmount();
    }
  });

  it('another change of the profile (a name, the appearance) reads nothing again', async () => {
    const m = await open();
    await m.result(m.call, 'base.profile.get', profile('en'));
    await m.result(m.call, 'base.profile.get', profile('en', { first_name: 'Ana María', theme_mode: 'dark' }), 2);
    expect(sessionChanged).not.toHaveBeenCalled();
  });

  it('a mode chosen anew (the assistant’s card) is painted at once: dark, light and the system’s', async () => {
    const m = await open();
    await m.result(m.call, 'base.profile.get', profile('en'));

    await m.result(m.call, 'base.profile.get', profile('en', { theme_mode: 'dark' }), 2);
    expect(themeMode.value).toBe('dark');
    expect(dark()).toBe(true);

    await m.result(m.call, 'base.profile.get', profile('en', { theme_mode: 'light' }), 3);
    expect(dark()).toBe(false);

    systemDark = true;
    await m.result(m.call, 'base.profile.get', profile('en', { theme_mode: 'system' }), 4);
    expect(themeMode.value).toBe('system');
    expect(dark()).toBe(true);
  });

  it('a palette and a scale chosen anew are painted, and back to the business’s appearance undoes them', async () => {
    const m = await open();
    await m.result(m.call, 'base.profile.get', profile('en'));

    await m.result(m.call, 'base.profile.get', profile('en', { theme_mode: 'dark', palette: 'forest', ui_scale: 110 }), 2);
    expect([themePalette.value, themeScale.value, dark()]).toEqual(['forest', 110, true]);

    await m.result(m.call, 'base.profile.get', profile('en', { theme_mode: 'dark', palette: 'forest', ui_scale: 120 }), 3);
    expect(themeScale.value).toBe(120);

    await m.result(m.call, 'base.profile.get', profile('en', { theme_mode: 'dark', palette: 'terracotta', ui_scale: 120 }), 4);
    expect(themePalette.value).toBe('terracotta');

    await m.result(m.call, 'base.profile.get', profile('en'), 5);
    expect([themeMode.value, themePalette.value, themeScale.value, dark()]).toEqual(['system', 'erplora', 100, false]);
  });

  it('the first answer paints nothing: the way in already painted the person’s appearance', async () => {
    const m = await open();
    await m.result(m.call, 'base.profile.get', profile('en', { theme_mode: 'dark' }));
    expect(themeMode.value).toBe('system');
    expect(dark()).toBe(false);
  });

  it('a new language alone leaves the appearance as it is', async () => {
    const m = await open();
    await m.result(m.call, 'base.profile.get', profile('en'));
    document.documentElement.classList.add('ion-palette-dark');
    await m.result(m.call, 'base.profile.get', profile('es'), 2);
    expect(dark()).toBe(true);
    expect(sessionChanged).toHaveBeenCalledTimes(1);
  });
});
