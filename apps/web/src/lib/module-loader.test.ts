// @vitest-environment happy-dom
//
// `loadMenu()` must never answer «this hub has no apps» when what actually happened is «I could not
// build the list» (hub#894).
//
// hub#770 wrote the rule and the state machine for it: loading, failed and empty are three
// different sentences, `moduleNavState` carries which one, and `refreshModuleNav()` marks `error`
// when `loadMenu()` REJECTS. Its tests mock `loadMenu` and make the mock reject, so they pass.
//
// The real `loadMenu` never rejected. It opened with `try { … } catch { return [] }` around the
// `/api/navigation` fetch, so a 401 — the everyday shape of a session displaced by a second device
// on the Free plan — arrived at `refreshModuleNav` as a successful empty list. `moduleNavState` went
// to `ready`, and `ready` + zero rows is painted «you have no apps yet».
//
// That is how a real production hub (`peluqueria-mac-qa`) with 12/12 modules registered per
// `/readyz`, whose till had taken 30,90 € hours earlier, ended up telling its owner it had no apps
// and offering to install the first one — on BOTH surfaces that list apps, with nothing in the
// console and nothing in the runtime log but the 401 itself.
//
// So the contract is pinned HERE, against the real fetch, and not against a mock of the very
// function whose behaviour was wrong.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));
vi.mock('./icons', () => ({ moduleIconRegistry: (i: Record<string, string>) => i }));
vi.mock('ionicons', () => ({ addIcons: () => {} }));
vi.mock('../i18n', () => ({ getLocale: () => 'es' }));

const entitled = vi.fn<(moduleId: string) => boolean>(() => true);
vi.mock('./entitlement', () => ({ isModuleEntitled: (id: string) => entitled(id) }));

import { loadMenu } from './module-loader';

/** One `/api/navigation` entry, as the runtime serves it. */
function navItem(moduleId: string) {
  return {
    module_id: moduleId,
    module_name: moduleId,
    id: `${moduleId}-main`,
    label: moduleId,
    icon: 'cube-outline',
    component: `erp-${moduleId}`,
  };
}

/**
 * Stubs `fetch` for the two URLs `loadMenu` walks: the navigation and each module's `module.json`.
 * `nav` is either a body to answer 200 with, or an HTTP status to fail with.
 */
function stubFetch(
  nav: { ok: boolean; data?: unknown[]; installed?: number } | number,
  manifests: Record<string, unknown | null> = {},
) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/api/navigation')) {
      if (typeof nav === 'number') {
        return { ok: false, status: nav, json: async () => ({}) } as unknown as Response;
      }
      return { ok: true, status: 200, json: async () => nav } as unknown as Response;
    }
    const match = /^\/modules\/([^/]+)\/module\.json$/.exec(url);
    if (match) {
      const manifest = manifests[match[1]];
      if (!manifest) return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
      return { ok: true, status: 200, json: async () => manifest } as unknown as Response;
    }
    // icons.json and locales: absent is the normal case and must not matter here.
    return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const inventoryManifest = { name: 'Inventory', ui: { entry: 'dist/inventory.esm.js' } };

beforeEach(() => {
  vi.unstubAllGlobals();
  entitled.mockReset();
  entitled.mockReturnValue(true);
});

describe('loadMenu builds the launcher', () => {
  it('returns one entry per navigation item of every installed module', async () => {
    stubFetch({ ok: true, data: [navItem('inventory')], installed: 1 }, { inventory: inventoryManifest });

    const entries = await loadMenu();

    expect(entries.map((e) => e.moduleId)).toEqual(['inventory']);
    expect(entries[0].entryUrl).toBe('/modules/inventory/dist/inventory.esm.js');
  });

  it('a hub where nothing is installed answers an empty list — that is a real answer', async () => {
    stubFetch({ ok: true, data: [], installed: 0 });

    await expect(loadMenu()).resolves.toEqual([]);
  });
});

// ── The bug: a failure that came out as «you have no apps» ────────────────────────────────────

describe('a failed navigation is a FAILURE, not an empty hub', () => {
  it('rejects when the runtime refuses the session (401)', async () => {
    // The production case. A second device signs in on the Free plan, this session is displaced,
    // and every session-guarded route answers 401 — while the shell still holds its `isAuthed`
    // from localStorage and looks logged in.
    stubFetch(401);

    await expect(loadMenu()).rejects.toThrow(/401/);
  });

  it('rejects when the runtime errors (500)', async () => {
    stubFetch(500);

    await expect(loadMenu()).rejects.toThrow(/500/);
  });

  it('rejects when there is no runtime to ask', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    await expect(loadMenu()).rejects.toThrow();
  });
});

// ── The safety net: an empty launcher on a hub that HAS modules is a contradiction ────────────
//
// Everything above is about the fetch failing. These are about it SUCCEEDING and the launcher coming
// out empty anyway, because something inside `loadMenu` dropped every module on the floor. Each drop
// was a silent `continue`, and the result was the same false sentence.
//
// The runtime now reports `installed` (hub#894), so the contradiction «zero apps to show, N modules
// installed» is detectable in the one place that knows both numbers.

describe('an empty launcher on a hub with modules installed is an error', () => {
  it('rejects when the entitlement filter drops every module', async () => {
    // `isModuleEntitled` is strict as soon as `/api/entitlement` resolves, and it resolves to an
    // empty Set whenever the SaaS answers 200 with no modules. Twelve installed modules then
    // vanished from the launcher with no error anywhere — the most plausible silent total wipe.
    entitled.mockReturnValue(false);
    stubFetch(
      { ok: true, data: [navItem('inventory'), navItem('sales')], installed: 2 },
      { inventory: inventoryManifest },
    );

    await expect(loadMenu()).rejects.toThrow();
  });

  it('rejects when no module manifest can be read', async () => {
    // `/modules/<id>/module.json` is served by the runtime itself. When it stops answering, every
    // module is skipped for want of a bundle to import, and the launcher empties out.
    stubFetch({ ok: true, data: [navItem('inventory')], installed: 1 }, {});

    await expect(loadMenu()).rejects.toThrow();
  });

  it('still returns the modules it COULD resolve when only some fail', async () => {
    // Data wins (hub#770): one broken module must not take the other eleven off the screen.
    stubFetch(
      { ok: true, data: [navItem('inventory'), navItem('broken')], installed: 2 },
      { inventory: inventoryManifest },
    );

    const entries = await loadMenu();

    expect(entries.map((e) => e.moduleId)).toEqual(['inventory']);
  });

  it('does not invent a contradiction on a runtime that does not report the count', async () => {
    // An older runtime omits `installed`. Absent is «I did not say», and «I did not say» can never
    // be the reason to shout: the answer is taken at face value, exactly as before.
    stubFetch({ ok: true, data: [] });

    await expect(loadMenu()).resolves.toEqual([]);
  });
});
