// The person's own language followed on every screen: base keeps the live `base.profile.get` open once per person
// and, when the language kept in «My profile» changes (the assistant's card, another tab), reads the session again,
// whose language the shell follows, so the open app speaks it without a reload. It paints nothing.
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { openFollower } from '../__tests__/followers';
import { OWNER } from '../__tests__/mount-base';
import { sessionChanged } from '../lib/access';
import type { Profile, ProfileLanguage } from '../operations/profile';
import LanguageFollower from './LanguageFollower.vue';

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

const open = () => openFollower(LanguageFollower, { session: me, path: '/', screens: [] });

beforeEach(() => {
  vi.mocked(sessionChanged).mockClear();
});
afterEach(() => {
  document.body.innerHTML = '';
});

describe('LanguageFollower', () => {
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
});
