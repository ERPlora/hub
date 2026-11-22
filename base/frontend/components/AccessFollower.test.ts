// What the signed-in person may do, followed on every screen: base keeps the live `base.session.access` open once per
// person and, when its key changes (erplora.com changed their role), reads the session again without signing in
// again, so the menu and the screen in front follow the new role. It paints nothing.
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { mountBase, OWNER } from '../__tests__/mount-base';
import { sessionChanged } from '../lib/access';
import AccessFollower from './AccessFollower.vue';

const me = ref<SessionMe | undefined>();
vi.mock('@erplora/ui/shell', async (importOriginal) => {
  const shell = await importOriginal<typeof import('@erplora/ui/shell')>();
  return { ...shell, useSession: () => shell.createShellSession(me, ref('live')) };
});
vi.mock('../lib/access', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/access')>()),
  sessionChanged: vi.fn(),
}));

async function open(path = '/') {
  const m = await mountBase(AccessFollower, { path });
  await m.router.replace(path);
  const call = await m.live();
  return { ...m, call };
}

beforeEach(() => {
  me.value = OWNER;
  vi.mocked(sessionChanged).mockClear();
});
afterEach(() => {
  document.body.innerHTML = '';
});

describe('AccessFollower', () => {
  it('follows the person’s access live and paints nothing', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.session.access').map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.text()).toBe('');
  });

  it('the first answer reads nothing again; a new key does, once', async () => {
    const m = await open();
    await m.result(m.call, 'base.session.access', { key: 'employee' });
    expect(sessionChanged).not.toHaveBeenCalled();

    await m.result(m.call, 'base.session.access', { key: 'manager' }, 2);
    expect(sessionChanged).toHaveBeenCalledTimes(1);

    await m.result(m.call, 'base.session.access', { key: 'manager' }, 3);
    expect(sessionChanged).toHaveBeenCalledTimes(1);

    await m.result(m.call, 'base.session.access', { key: 'employee' }, 4);
    expect(sessionChanged).toHaveBeenCalledTimes(2);
  });
});
