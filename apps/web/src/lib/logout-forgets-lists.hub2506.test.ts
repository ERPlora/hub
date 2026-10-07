// @vitest-environment happy-dom
// hub#2506 — **signing out forgets the lists the shell built for that person.**
//
// On a shared till the next person signs in right after: the shell re-reads the launcher and the
// setup checklist then, but both stores keep their last good answer when a read fails (on purpose,
// for a refresh of the SAME person). So a sign-out that leaves them standing hands the previous
// person's apps and checklist to whoever signs in next, the moment one read fails. Signing out
// empties them; the next sign-in fills them for whoever arrives.
import { describe, expect, it, vi } from 'vitest';

const loadMenu = vi.fn();
vi.mock('./module-loader', () => ({ loadMenu: () => loadMenu(), invalidateManifestCache: vi.fn() }));
vi.mock('./cloud', () => ({ runtimeLogout: vi.fn(), clearTokens: vi.fn() }));
vi.mock('./user-profile', () => ({ resetUserProfile: vi.fn() }));
vi.mock('./theme', () => ({ resetUserThemePreferences: vi.fn() }));
vi.mock('../i18n', () => ({ resetUserLocale: vi.fn() }));
vi.mock('./entitlement', () => ({ resetEntitlement: vi.fn() }));
vi.mock('./assistant-history', () => ({ clearAssistantHistory: vi.fn() }));
vi.mock('./dead-letter', () => ({ stopDeadLetterWatch: vi.fn() }));

import { logout, setHubSession } from './session';
import { moduleNav, refreshModuleNav } from './nav';
import { refreshSetupStatus, setupStatus } from './setup-status';

const settle = () => new Promise((r) => setTimeout(r, 20));

describe('signing out', () => {
  it('forgets the launcher and the setup checklist of the person who leaves', async () => {
    setHubSession('sess-ana');
    loadMenu.mockResolvedValue([
      { moduleId: 'reports', moduleName: 'Reports', nav: { id: 'overview', label: 'Overview', icon: '' } },
    ]);
    await refreshModuleNav();
    await refreshSetupStatus({
      query: async () => ({ total: 1, pending: 1, items: [{ key: 'manager-only-step', state: 'pending' }] }),
    } as never);
    // Sanity: her lists really are on screen.
    expect(moduleNav.value.map((m) => m.path)).toEqual(['/m/reports']);
    expect(setupStatus.value?.items.map((i) => i.key)).toEqual(['manager-only-step']);

    logout();
    await settle();

    expect(moduleNav.value).toEqual([]);
    expect(setupStatus.value).toBeNull();
  });
});
