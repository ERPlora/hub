// hub#775 — tests of the shell half of the `protects` route guard.
//
// The runtime's dispatcher is the authoritative half (every `sales.*` command refused while the
// drawer is closed). This util is the cosmetic half: it tells ModuleView whether to mount the POS
// or the "open the drawer" screen. These tests pin its resolution so it AGREES with the runtime
// by construction: same armming rule (settings + enabled_setting), same route match, same
// precondition (guard_query non-empty), and the same degrade-OPEN policy on any read failure
// (a till that refuses to render over a broken read is a worse failure than one that renders and
// lets the dispatcher refuse).
import { describe, it, expect, vi, beforeEach } from 'vitest';

const loadManifest = vi.fn();
const listInstalledModules = vi.fn();

vi.mock('./module-loader', () => ({
  loadManifest: (...a: unknown[]) => loadManifest(...a),
}));
vi.mock('./runtime', () => ({
  listInstalledModules: (...a: unknown[]) => listInstalledModules(...a),
}));

import { resolveProtectsGuard, routeCoversPath } from './protects';
import type { ErploraClient } from '@erplora/module-sdk';

/** Minimal client double: `query` dispatches on the query name to a mutable answer per test. */
function makeClient(answers: Record<string, unknown>) {
  const query = vi.fn(async (name: string) => {
    if (name in answers) return answers[name];
    throw new Error(`query ${name} not stubbed`);
  });
  return { query, client: { query } as unknown as ErploraClient };
}

const CASH_REGISTER_PROTECTS = [
  {
    settings_query: 'cash_register.settings.get',
    enabled_setting: 'enable_cash_register',
    route_setting: 'protected_pos_url',
    guard_query: 'cash_register.current_session',
    expect: 'non_empty' as const,
    component: 'erp-cashregister-open',
    resume_on: 'cash_register.session_opened',
  },
];

function cashRegisterSettings(over: Record<string, unknown> = {}) {
  return [
    {
      enable_cash_register: 1,
      protected_pos_url: '/m/sales/pos/',
      ...over,
    },
  ];
}

describe('routeCoversPath', () => {
  it('matches an exact route and a deeper navId under it', () => {
    expect(routeCoversPath('/m/sales', '/m/sales')).toBe(true);
    expect(routeCoversPath('/m/sales', '/m/sales/pos')).toBe(true);
    expect(routeCoversPath('/m/sales/pos/', '/m/sales/pos')).toBe(true);
  });
  it('does not match a sibling module that shares a prefix', () => {
    expect(routeCoversPath('/m/sales', '/m/salesforce')).toBe(false);
  });
  it('does not match an empty guard route', () => {
    expect(routeCoversPath('', '/m/sales')).toBe(false);
  });
});

describe('resolveProtectsGuard', () => {
  beforeEach(() => {
    loadManifest.mockReset();
    listInstalledModules.mockReset();
  });

  it('arms and reports the guard when the drawer is closed', async () => {
    listInstalledModules.mockResolvedValue([{ id: 'cash_register', status: 'active' }]);
    loadManifest.mockResolvedValue({ protects: CASH_REGISTER_PROTECTS });
    const { client } = makeClient({
      'cash_register.settings.get': cashRegisterSettings(),
      'cash_register.current_session': [], // drawer closed → precondition unmet
    });

    const guard = await resolveProtectsGuard(client, '/m/sales/pos');

    expect(guard).not.toBeNull();
    expect(guard?.declaringModule).toBe('cash_register');
    expect(guard?.def.component).toBe('erp-cashregister-open');
    expect(guard?.def.resume_on).toBe('cash_register.session_opened');
  });

  it('does not arm when the route is not the protected one', async () => {
    listInstalledModules.mockResolvedValue([{ id: 'cash_register', status: 'active' }]);
    loadManifest.mockResolvedValue({ protects: CASH_REGISTER_PROTECTS });
    const { client } = makeClient({
      'cash_register.settings.get': cashRegisterSettings(),
      'cash_register.current_session': [],
    });

    const guard = await resolveProtectsGuard(client, '/m/inventory');

    expect(guard).toBeNull();
  });

  it('returns null when the guard is disabled (enable_cash_register = false)', async () => {
    listInstalledModules.mockResolvedValue([{ id: 'cash_register', status: 'active' }]);
    loadManifest.mockResolvedValue({ protects: CASH_REGISTER_PROTECTS });
    const { client } = makeClient({
      'cash_register.settings.get': cashRegisterSettings({ enable_cash_register: 0 }),
      'cash_register.current_session': [],
    });

    const guard = await resolveProtectsGuard(client, '/m/sales/pos');

    expect(guard).toBeNull();
  });

  it('returns null when the drawer is open (precondition met)', async () => {
    listInstalledModules.mockResolvedValue([{ id: 'cash_register', status: 'active' }]);
    loadManifest.mockResolvedValue({ protects: CASH_REGISTER_PROTECTS });
    const { client } = makeClient({
      'cash_register.settings.get': cashRegisterSettings(),
      'cash_register.current_session': [{ id: 'sess-1', expected_total: 0 }],
    });

    const guard = await resolveProtectsGuard(client, '/m/sales/pos');

    expect(guard).toBeNull();
  });

  it('degrades OPEN when a read fails (the dispatcher is authoritative)', async () => {
    listInstalledModules.mockResolvedValue([{ id: 'cash_register', status: 'active' }]);
    loadManifest.mockResolvedValue({ protects: CASH_REGISTER_PROTECTS });
    const { client } = makeClient({
      'cash_register.settings.get': cashRegisterSettings(),
      // guard_query not stubbed → makeClient throws → util must skip, not report
    });

    const guard = await resolveProtectsGuard(client, '/m/sales/pos');

    expect(guard).toBeNull();
  });

  it('skips inactive modules', async () => {
    listInstalledModules.mockResolvedValue([{ id: 'cash_register', status: 'inactive' }]);
    loadManifest.mockResolvedValue({ protects: CASH_REGISTER_PROTECTS });
    const { client } = makeClient({});

    const guard = await resolveProtectsGuard(client, '/m/sales/pos');

    expect(guard).toBeNull();
    expect(loadManifest).not.toHaveBeenCalled();
  });
});
