// The apps of the business followed on every screen (PLAN-HUB §9; BASE-F22): base keeps the live `base.app.list` open
// once per signed-in person and, when an app is turned on or off (here or on another device), reads the session
// again, so the menu says it without a reload; a screen of an app that went off is sent through the app gate again,
// which shows why it does not open. It paints nothing.
import type { SessionMe } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { flush, mountBase, OWNER } from '../__tests__/mount-base';
import { sessionChanged } from '../lib/access';
import type { AppList, AppRow } from '../operations';
import AppsFollower from './AppsFollower.vue';

const me = ref<SessionMe | undefined>();
vi.mock('@erplora/ui/shell', async (importOriginal) => {
  const shell = await importOriginal<typeof import('@erplora/ui/shell')>();
  return { ...shell, useSession: () => shell.createShellSession(me, ref('live')) };
});
vi.mock('../lib/access', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/access')>()),
  sessionChanged: vi.fn(),
}));

function row(id: string, state: AppRow['state'] = 'on'): AppRow {
  return {
    id,
    name: id,
    icon: 'ion:cube-outline',
    category: 'sales',
    category_label: 'Sales',
    summary: '',
    premium: false,
    right: 'free',
    state,
    chosen: true,
    path: state === 'on' ? `/${id}/home` : null,
    requires: [],
    required_by: [],
  };
}

function list(...apps: AppRow[]): AppList {
  return { apps, store_url: '', plan_url: '', max_apps: null, enabled: apps.length };
}

function session(states: Record<string, 'on' | 'off'>): SessionMe {
  return { ...OWNER, apps: Object.entries(states).map(([label, state]) => ({ label, state })) };
}

async function open(path = '/') {
  const m = await mountBase(AppsFollower, { path, routes: ['/apps'] });
  m.router.addRoute({ path: '/task/home', component: { template: '<div />' }, meta: { auth: true, app: 'task' } });
  m.router.addRoute({ path: '/sale/home', component: { template: '<div />' }, meta: { auth: true, app: 'sale' } });
  await m.router.replace(path);
  const call = await m.live();
  return { ...m, call };
}

beforeEach(() => {
  me.value = session({ task: 'on', sale: 'on' });
  vi.mocked(sessionChanged).mockClear();
});
afterEach(() => {
  document.body.innerHTML = '';
});

describe('AppsFollower', () => {
  it('follows the business’s apps live and paints nothing', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.app.list').map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.text()).toBe('');
  });

  it('the first answer reads nothing again; an app turned on or off does, once', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', list(row('task'), row('sale')));
    expect(sessionChanged).not.toHaveBeenCalled();

    await m.result(m.call, 'base.app.list', list(row('task', 'off'), row('sale')), 2);
    expect(sessionChanged).toHaveBeenCalledTimes(1);

    // Nothing turned on or off (the plan's limit, a name): the session stays.
    await m.result(m.call, 'base.app.list', { ...list(row('task', 'off'), row('sale')), max_apps: 20 }, 3);
    expect(sessionChanged).toHaveBeenCalledTimes(1);

    await m.result(m.call, 'base.app.list', list(row('task'), row('sale')), 4);
    expect(sessionChanged).toHaveBeenCalledTimes(2);
  });

  it('on a screen of an app that went off, the gate runs again (it shows why it does not open)', async () => {
    const m = await open('/task/home');
    const gate = vi.fn(() => true as const);
    m.router.beforeEach(gate);

    me.value = session({ task: 'off', sale: 'on' });
    await flush();

    expect(gate).toHaveBeenCalledTimes(1);
    expect(m.router.currentRoute.value.fullPath).toBe('/task/home');
  });

  it('a screen of another app, or of base, is left where it is', async () => {
    const m = await open('/sale/home');
    const gate = vi.fn(() => true as const);
    m.router.beforeEach(gate);

    me.value = session({ task: 'off', sale: 'on' });
    await flush();

    expect(gate).not.toHaveBeenCalled();
  });
});
