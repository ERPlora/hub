// What the signed-in person may do, followed on every screen: base keeps the live `base.session.access` open once per
// person and, when its key changes (erplora.com changed their role), reads the session again without signing in
// again, so the menu follows the new role; a screen in front that the new session closes or opens goes through the
// app gate again («No access», or the screen). It paints nothing.
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { flush, mountBase, OWNER } from '../__tests__/mount-base';
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

/** Taxes' «Rules» is open to a manager and closed to an employee; the till is open to both. */
const MANAGER: SessionMe = {
  ...OWNER,
  menu: [
    { id: 'tax', label: 'Taxes', items: [{ path: '/tax/rules', label: 'Rules', icon: 'ion:list-outline' }] },
    { id: 'sale', label: 'Sales', items: [{ path: '/sale/pos', label: 'Till', icon: 'ion:cart-outline' }] },
  ],
  apps: [
    { label: 'tax', state: 'on' },
    { label: 'sale', state: 'on' },
  ],
  locked: {},
};
const EMPLOYEE: SessionMe = { ...MANAGER, menu: MANAGER.menu.slice(1), locked: { tax: ['/tax/rules'] } };

async function open(path = '/') {
  const m = await mountBase(AccessFollower, { path });
  m.router.addRoute({ path: '/tax/rules', component: { template: '<div />' }, meta: { auth: true, app: 'tax' } });
  m.router.addRoute({ path: '/sale/pos', component: { template: '<div />' }, meta: { auth: true, app: 'sale' } });
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

  it.each([
    ['closes', MANAGER, EMPLOYEE],
    ['opens', EMPLOYEE, MANAGER],
  ])('a session that %s the screen in front runs the gate again in the same address', async (_, before, after) => {
    me.value = before;
    const m = await open('/tax/rules');
    const gate = vi.fn(() => true as const);
    m.router.beforeEach(gate);

    me.value = after;
    await flush();

    expect(gate).toHaveBeenCalledTimes(1);
    expect(m.router.currentRoute.value.fullPath).toBe('/tax/rules');
  });

  it('a screen the new session neither closes nor opens is left where it is', async () => {
    me.value = MANAGER;
    const m = await open('/sale/pos');
    const gate = vi.fn(() => true as const);
    m.router.beforeEach(gate);

    me.value = EMPLOYEE;
    await flush();

    expect(gate).not.toHaveBeenCalled();
  });
});
