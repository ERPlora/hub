// @vitest-environment happy-dom
//
// hub#1175 — the checklist pointed at `invoice_series`, a module RETIRED from the marketplace
// that stayed installed+active in an older hub. Its "Configurar" button led to `/m/invoice_series`,
// and the guard under test bounced that navigation straight back to `/dashboard` with nothing
// said: no toast, no modal — QA had to read the network tab to learn the runtime's own dispatcher
// was refusing the module with `module_entitlement_blocked` (402).
//
// `isModuleEntitled` cannot tell the two reasons apart on its own: a module the revalidation
// BLOCKED (present in `revalidation.blocked_modules`, `lib/entitlement.ts`) still deserves a
// screen — `ModuleView.vue` already renders a `blocked-card` explaining exactly why, the same
// card a module blocked for non-payment gets. A module the entitlement never named at all has no
// screen to give, and that bounce needs a reason of its own instead of vanishing silently.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RouteLocationNormalized } from 'vue-router';

import { setUser } from '../lib/session';

vi.mock('../lib/entitlement', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/entitlement')>();
  return { ...actual, isModuleEntitled: vi.fn(), isModuleBlocked: vi.fn() };
});

const { toastInfoSpy } = vi.hoisted(() => ({ toastInfoSpy: vi.fn() }));
vi.mock('../lib/toast', () => ({ toastInfo: toastInfoSpy, toastError: vi.fn(), toastSuccess: vi.fn() }));

import { isModuleBlocked, isModuleEntitled } from '../lib/entitlement';
import { authGate } from './index';

const isModuleEntitledMock = vi.mocked(isModuleEntitled);
const isModuleBlockedMock = vi.mocked(isModuleBlocked);

function moduleRoute(moduleId: string): RouteLocationNormalized {
  return {
    name: 'module',
    path: `/m/${moduleId}`,
    fullPath: `/m/${moduleId}`,
    hash: '',
    query: {},
    params: { moduleId },
    meta: { auth: true },
  } as unknown as RouteLocationNormalized;
}

const ANA = { id: 'local-1', name: 'Ana', email: 'ana@example.com', role: 'owner', permissions: ['*'] };

describe('router module gate: entitlement-blocked vs. never-entitled (hub#1175)', () => {
  beforeEach(() => {
    setUser(ANA);
    isModuleEntitledMock.mockReset();
    isModuleBlockedMock.mockReset();
    toastInfoSpy.mockReset();
  });

  it('lets a route MOUNT when the entitlement revalidation named it blocked, so `blocked-card` can explain why', async () => {
    isModuleEntitledMock.mockReturnValue(false);
    isModuleBlockedMock.mockReturnValue(true);

    await expect(authGate(moduleRoute('invoice_series'))).resolves.toBe(true);
    expect(toastInfoSpy).not.toHaveBeenCalled(); // the card on screen says why; no toast needed too
  });

  it('still bounces a module the entitlement never named at all — but now WITH a reason', async () => {
    isModuleEntitledMock.mockReturnValue(false);
    isModuleBlockedMock.mockReturnValue(false);

    const decision = await authGate(moduleRoute('ghost_module'));
    expect(decision).toEqual({ name: 'dashboard' });
    expect(toastInfoSpy).toHaveBeenCalledTimes(1);
  });

  it('lets an entitled module through untouched, exactly as before', async () => {
    isModuleEntitledMock.mockReturnValue(true);
    isModuleBlockedMock.mockReturnValue(false);

    await expect(authGate(moduleRoute('inventory'))).resolves.toBe(true);
    expect(toastInfoSpy).not.toHaveBeenCalled();
  });
});
