// @vitest-environment happy-dom
// hub#2506 — **after a hand-over the till shows what the person who ARRIVED may use, not what the
// person who left could.**
//
// The hand-over (`switchUser`, hub#456) swaps the session without navigating, so nothing re-reads
// the three lists the shell built for the previous person: the apps of the launcher and of «My apps»
// (`moduleNav`, filtered by the runtime with HER permissions), the plan resolved with HER erplora.com
// credentials (`entitlement`, which the hand-over has just taken off the till) and the setup
// checklist (`setupStatus`, whose actions depend on who reads it). The shell only re-reads them when
// `isAuthed` flips, and a hand-over never flips it: the manager's apps stayed in the cashier's
// launcher until the page was reloaded.
//
// Pinned here against the REAL stores (`nav.ts`, `entitlement.ts`, `setup-status.ts`): only the
// network behind them is stubbed. And the failure half: when a re-read fails, the previous person's
// list is NOT what stays on screen — the screen says it could not load, it does not keep hers.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const runtimePinLogin = vi.fn();
const cloudEntitlement = vi.fn();
vi.mock('./cloud', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./cloud')>()),
  runtimePinLogin: (name: string, pin: string) => runtimePinLogin(name, pin),
  runtimeLogout: vi.fn(async () => {}),
  cloudEntitlement: () => cloudEntitlement(),
}));

// The real loader drops every module the plan does not entitle (`isModuleEntitled`, §2.10); the
// double keeps that one rule so the ORDER plan → launcher is observable.
const loadMenu = vi.fn();
vi.mock('./module-loader', async () => {
  const { isModuleEntitled } = await import('./entitlement');
  return {
    loadMenu: async () =>
      ((await loadMenu()) as Array<{ moduleId: string }>).filter((e) => isModuleEntitled(e.moduleId)),
    invalidateManifestCache: vi.fn(),
  };
});

const query = vi.fn();
vi.mock('./runtime', () => ({
  getClient: () => ({ query: (name: string) => query(name) }),
  ensureMediaCookie: vi.fn(async () => {}),
  refreshActiveModuleIds: vi.fn(async () => {}),
}));

vi.mock('./user-profile', () => ({ getUserProfile: vi.fn(async () => null), resetUserProfile: vi.fn() }));
vi.mock('./theme', () => ({ resetUserThemePreferences: vi.fn() }));
vi.mock('../i18n', () => ({ resetUserLocale: vi.fn(), getLocale: () => 'es' }));

import { switchUser } from './user-switch';
import { setHubSession, setUser } from './session';
import { setTokens } from './cloud';
import { moduleNav, moduleNavState, refreshModuleNav } from './nav';
import { entitlementStatus, isModuleBlocked, resolveEntitlement } from './entitlement';
import { refreshSetupStatus, setupStatus, SETUP_STATUS_QUERY } from './setup-status';

const MANAGER_MENU = [
  { moduleId: 'reports', moduleName: 'Reports', nav: { id: 'overview', label: 'Overview', icon: '' } },
  { moduleId: 'sales', moduleName: 'Sales', nav: { id: 'pos', label: 'Sell', icon: '' } },
];
const CASHIER_MENU = [{ moduleId: 'sales', moduleName: 'Sales', nav: { id: 'pos', label: 'Sell', icon: '' } }];

function checklist(key: string) {
  return { done: 0, total: 1, items: [{ key, state: 'pending', level: 'functional', title: key, origin: 'user' }] };
}

/** The manager at the till: signed in with her account, her lists already on screen. */
async function seedManagerShift(): Promise<void> {
  setUser({ id: 'u-ana', name: 'Ana', email: 'ana@erplora.test', role: 'manager', permissions: ['*'] });
  setHubSession('sess-ana');
  setTokens('acc-ana', 'ref-ana');

  cloudEntitlement.mockResolvedValue({
    modules: [{ moduleId: 'reports' }, { moduleId: 'sales' }],
    blockedModules: ['reports'],
  });
  await resolveEntitlement();
  loadMenu.mockResolvedValue(MANAGER_MENU);
  await refreshModuleNav();
  query.mockResolvedValue(checklist('manager-only-step'));
  await refreshSetupStatus({ query } as never);
}

beforeEach(async () => {
  localStorage.clear();
  sessionStorage.clear();
  runtimePinLogin.mockReset();
  cloudEntitlement.mockReset();
  loadMenu.mockReset();
  query.mockReset();
  await seedManagerShift();
  // Sanity: the seed really put HER lists on screen, or the assertions below would prove nothing.
  expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/reports', '/m/sales']);
  expect(isModuleBlocked('reports')).toBe(true);
  expect(setupStatus.value?.items.map((i) => i.key)).toEqual(['manager-only-step']);

  runtimePinLogin.mockResolvedValue({
    token: 'sess-leo',
    credential_kind: 'pin',
    user: { id: 'u-leo', name: 'Leo', role: 'employee' },
    permissions: ['sales.view'],
  });
});

describe('the hand-over re-reads what the shell built for the person who left', () => {
  it('shows the launcher of the person who arrived', async () => {
    loadMenu.mockResolvedValue(CASHIER_MENU);
    query.mockResolvedValue(checklist('cashier-step'));

    await switchUser('Leo', '1357');

    expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/sales']);
    expect(moduleNavState.value).toBe('ready');
  });

  it('forgets the plan resolved with the previous person’s erplora.com account', async () => {
    loadMenu.mockResolvedValue(CASHIER_MENU);
    query.mockResolvedValue(checklist('cashier-step'));

    await switchUser('Leo', '1357');

    // The arriving PIN session carries no erplora.com credentials, so there is nothing to resolve
    // the plan with: the gate goes back to «not resolved», never to the leaver's snapshot.
    expect(entitlementStatus.value).toBe('unknown');
    expect(isModuleBlocked('reports')).toBe(false);
    expect(cloudEntitlement).toHaveBeenCalledTimes(1); // only the seed — never with her token again
  });

  it('gates the launcher with the plan of the person who arrived, not the one resolved for the leaver', async () => {
    // `tables` was not in the plan resolved with the manager's account. The arriving PIN session has
    // no account to resolve one with, so the gate is back to «not resolved» (permissive) BEFORE the
    // launcher is re-read — read in the other order, the leaver's plan would still be filtering it.
    loadMenu.mockResolvedValue([
      ...CASHIER_MENU,
      { moduleId: 'tables', moduleName: 'Tables', nav: { id: 'floor', label: 'Floor', icon: '' } },
    ]);
    query.mockResolvedValue(checklist('cashier-step'));

    await switchUser('Leo', '1357');

    expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/sales', '/m/tables']);
  });

  it('re-reads the setup checklist for the person who arrived', async () => {
    loadMenu.mockResolvedValue(CASHIER_MENU);
    query.mockResolvedValue(checklist('cashier-step'));

    await switchUser('Leo', '1357');

    expect(query).toHaveBeenLastCalledWith(SETUP_STATUS_QUERY);
    expect(setupStatus.value?.items.map((i) => i.key)).toEqual(['cashier-step']);
  });

  it('does not keep the previous person’s lists when the re-read fails', async () => {
    loadMenu.mockRejectedValue(new Error('offline'));
    query.mockRejectedValue(new Error('offline'));

    await switchUser('Leo', '1357');

    expect(moduleNav.value).toEqual([]);
    expect(moduleNavState.value).toBe('error');
    expect(setupStatus.value).toBeNull();
  });

  it('touches none of them when the PIN is refused', async () => {
    runtimePinLogin.mockReset();
    runtimePinLogin.mockRejectedValue(new Error('refused'));

    await expect(switchUser('Leo', '0000')).rejects.toThrow();

    expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/reports', '/m/sales']);
    expect(isModuleBlocked('reports')).toBe(true);
    expect(setupStatus.value?.items.map((i) => i.key)).toEqual(['manager-only-step']);
    expect(loadMenu).toHaveBeenCalledTimes(1); // the seed only
  });
});
