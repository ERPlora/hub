// @vitest-environment happy-dom
// hub#2539 / hub#2538 — **after a hand-over nothing the previous person was looking at stays on
// screen**: not the page under the overlay, not the pages Ionic keeps hidden for «back», not the
// assistant panel with her unsent text, attachments, quota notice or setup mode.
//
// The hand-over (`switchUser`, hub#456) swaps the session without navigating, by design: the sale in
// progress must survive it. But the screens MOUNTED for the person who left kept rendering what they
// had read with her session. The shell cannot ask every screen to forget; it can mount them again
// for whoever arrived — which is what `handovers` tells App.vue to do — and, when she may not open
// the screen at all, take the till to Home first (`screenAfterHandover`), so the forbidden screen is
// never mounted again under her session.
//
// The e2e half (`tests/e2e/UserSwitchLeavesNothingBehindHub2539.spec.ts`) proves the remount in a
// real browser; this pins the decision and the signal against the real stores.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const runtimePinLogin = vi.fn();
vi.mock('./cloud', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./cloud')>()),
  runtimePinLogin: (name: string, pin: string) => runtimePinLogin(name, pin),
  runtimeLogout: vi.fn(async () => {}),
  cloudEntitlement: vi.fn(async () => null),
}));
vi.mock('./module-loader', () => ({ loadMenu: vi.fn(async () => []), invalidateManifestCache: vi.fn() }));
vi.mock('./runtime', () => ({
  getClient: () => ({ query: vi.fn(async () => ({ done: 0, total: 0, items: [] })) }),
  ensureMediaCookie: vi.fn(async () => {}),
  refreshActiveModuleIds: vi.fn(async () => {}),
}));
vi.mock('./user-profile', () => ({ getUserProfile: vi.fn(async () => null), resetUserProfile: vi.fn() }));
vi.mock('./theme', () => ({ resetUserThemePreferences: vi.fn() }));
vi.mock('../i18n', () => ({ resetUserLocale: vi.fn(), getLocale: () => 'es' }));

import { handovers, screenAfterHandover, switchUser } from './user-switch';
import { logout, setHubSession, setUser } from './session';
import { assistantIntent, assistantOpen, openAssistantForSetup } from './shell';
import type { ModuleNavItem } from './nav';

const SALES: ModuleNavItem = {
  path: '/m/sales',
  label: 'Sales',
  icon: '',
  tabs: [
    { id: 'pos', label: 'Sell' },
    { id: 'history', label: 'History' },
  ],
};

function moduleRoute(moduleId: string, navId?: string) {
  return { name: 'module', params: navId ? { moduleId, navId } : { moduleId } };
}

describe('screenAfterHandover — where the till goes for the person who arrived', () => {
  it('stays on a screen of an app she may open', () => {
    expect(screenAfterHandover(moduleRoute('sales', 'pos'), [SALES], 'ready')).toBeNull();
    expect(screenAfterHandover(moduleRoute('sales'), [SALES], 'ready')).toBeNull();
  });

  it('goes Home from an app her launcher does not list', () => {
    expect(screenAfterHandover(moduleRoute('reports', 'figures'), [SALES], 'ready')).toBe('/dashboard');
  });

  it('goes Home from a screen of an allowed app that her permissions hide', () => {
    expect(screenAfterHandover(moduleRoute('sales', 'margins'), [SALES], 'ready')).toBe('/dashboard');
  });

  it('goes Home when her launcher could not be read: it cannot vouch for the screen', () => {
    expect(screenAfterHandover(moduleRoute('sales', 'pos'), [SALES], 'error')).toBe('/dashboard');
    expect(screenAfterHandover(moduleRoute('sales', 'pos'), [], 'loading')).toBe('/dashboard');
  });

  it('leaves the shell’s own screens where they are: each one re-reads for her when mounted again', () => {
    expect(screenAfterHandover({ name: 'settings', params: {} }, [], 'ready')).toBeNull();
    expect(screenAfterHandover({ name: 'dashboard', params: {} }, [], 'error')).toBeNull();
  });
});

describe('the hand-over tells the shell to mount the screen again and closes the assistant', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    runtimePinLogin.mockReset();
    setUser({ id: 'u-ana', name: 'Ana', email: 'ana@erplora.test', role: 'admin', permissions: ['*'] });
    setHubSession('sess-ana');
    openAssistantForSetup('fiscal');
    expect(assistantOpen.value).toBe(true);
    expect(assistantIntent.value).not.toBeNull();
  });

  it('counts the hand-over and closes the assistant, out of setup mode', async () => {
    runtimePinLogin.mockResolvedValue({
      token: 'sess-leo',
      credential_kind: 'pin',
      user: { id: 'u-leo', name: 'Leo', role: 'employee' },
      permissions: ['sales.view'],
    });
    const before = handovers.value;

    await switchUser('Leo', '1357');

    expect(handovers.value).toBe(before + 1);
    expect(assistantOpen.value).toBe(false);
    expect(assistantIntent.value).toBeNull();
  });

  it('touches nothing when the PIN is refused', async () => {
    runtimePinLogin.mockRejectedValue(new Error('refused'));
    const before = handovers.value;

    await expect(switchUser('Leo', '0000')).rejects.toThrow();

    expect(handovers.value).toBe(before);
    expect(assistantOpen.value).toBe(true);
    expect(assistantIntent.value).toEqual({ topic: 'setup', itemKey: 'fiscal' });
  });

  it('signing out also leaves setup mode, so the next person does not inherit it', async () => {
    logout();
    await vi.dynamicImportSettled();

    expect(assistantIntent.value).toBeNull();
    expect(assistantOpen.value).toBe(false);
  });
});
