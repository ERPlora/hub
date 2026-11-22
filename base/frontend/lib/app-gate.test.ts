import type { SessionMe } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import { ref } from 'vue';
import type { RouteLocationNormalized } from 'vue-router';

import { APP_BLOCKED_ROUTE, appOfRouteFile, createAppGate, gateVerdict } from './app-gate';

const ME: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['base.view_home'],
  menu: [],
  apps: [
    { label: 'tax', state: 'on' },
    { label: 'stock', state: 'off' },
  ],
  language: 'en',
};

function to(path: string, app?: string, extra: Partial<RouteLocationNormalized> = {}): RouteLocationNormalized {
  return { path, fullPath: path, query: {}, hash: '', meta: app ? { app } : {}, ...extra } as RouteLocationNormalized;
}

describe('the app of a route file', () => {
  it('is the folder of apps/<id>/frontend/routes.ts; base is none', () => {
    expect(appOfRouteFile('../apps/cash_register/frontend/routes.ts')).toBe('cash_register');
    expect(appOfRouteFile('../base/frontend/routes.ts')).toBeUndefined();
  });
});

describe('createAppGate', () => {
  const gate = createAppGate(ref(ME));

  it('lets an app that is on through', () => {
    expect(gate(to('/tax/rules', 'tax'))).toBe(true);
  });

  it('mounts «why it does not open» in the same address for an app that is off', () => {
    expect(gate(to('/stock/items/42', 'stock', { query: { q: 'x' }, hash: '#a' }))).toEqual({
      name: APP_BLOCKED_ROUTE.name,
      params: { pathMatch: ['stock', 'items', '42'] },
      query: { q: 'x' },
      hash: '#a',
    });
  });

  it('lets through a platform screen the person may open, an app the session does not list and a session not here yet', () => {
    expect(gate(to('/apps'))).toBe(true);
    expect(gate(to('/reports', 'reports'))).toBe(true);
    expect(createAppGate(ref(undefined))(to('/stock', 'stock'))).toBe(true);
  });

  it('is reached only by name: a catch-all registered after the 404, which keeps every unknown address', () => {
    expect(APP_BLOCKED_ROUTE).toMatchObject({ path: '/:pathMatch(.*)*', name: 'base-app-blocked', meta: { auth: true } });
  });
});

/** An employee: Staff's members open, its settings locked; Taxes, whose every screen is locked, it may not see at all. */
const EMPLOYEE: SessionMe = {
  user: { id: 'u2', label: 'Eva' },
  permissions: ['base.view_home', 'base.view_files'],
  menu: [
    { id: 'staff', label: 'Staff', items: [{ path: '/staff/members', label: 'Members', icon: 'ion:people-outline' }] },
    { id: 'reports', label: 'Reports', items: [{ path: '/reports/mine', label: 'Mine', icon: 'ion:person-outline' }] },
  ],
  apps: [
    { label: 'staff', state: 'on' },
    { label: 'reports', state: 'on' },
    { label: 'stock', state: 'off' },
  ],
  locked: {
    staff: ['/staff/settings'],
    tax: ['/tax/categories', '/tax/rules'],
    reports: ['/reports'],
    stock: ['/stock/items'],
  },
  language: 'en',
};

describe('the screens a person may not open', () => {
  const gate = createAppGate(ref(EMPLOYEE));

  it('say «No access» in the same address, under a locked entry of its app', () => {
    expect(gate(to('/staff/settings/roles', 'staff', { query: { tab: 'a' } }))).toEqual({
      name: APP_BLOCKED_ROUTE.name,
      params: { pathMatch: ['staff', 'settings', 'roles'] },
      query: { tab: 'a' },
      hash: '',
    });
    expect(gateVerdict(EMPLOYEE, to('/staff/settings', 'staff'))).toBe('no-access');
  });

  it('let through what an open entry covers', () => {
    expect(gate(to('/staff/members', 'staff'))).toBe(true);
    expect(gate(to('/staff/members/42', 'staff'))).toBe(true);
  });

  it('decide by the longest entry that covers the address, segment by segment', () => {
    expect(gateVerdict(EMPLOYEE, to('/reports/mine/2026', 'reports'))).toBe('open');
    expect(gateVerdict(EMPLOYEE, to('/reports/all', 'reports'))).toBe('no-access');
    expect(gateVerdict(EMPLOYEE, to('/staff/settings-old', 'staff'))).toBe('open');
  });

  it('close an app the person sees nothing of, by its locked entries and never by its apps', () => {
    expect(EMPLOYEE.apps.some((app) => app.label === 'tax')).toBe(false);
    expect(gateVerdict(EMPLOYEE, to('/tax/rules/ES', 'tax'))).toBe('no-access');
    expect(gateVerdict({ ...EMPLOYEE, locked: {} }, to('/tax/rules/ES', 'tax'))).toBe('open');
  });

  it('leave an app that does not open to «why it does not open», which holds for everyone', () => {
    expect(gateVerdict(EMPLOYEE, to('/stock/items', 'stock'))).toBe('blocked');
  });

  it('lock nothing to a session that names no locked entry, or before it arrives', () => {
    expect(gateVerdict({ ...EMPLOYEE, locked: undefined }, to('/staff/settings', 'staff'))).toBe('open');
    expect(gateVerdict(undefined, to('/staff/settings', 'staff'))).toBe('open');
    expect(gateVerdict(EMPLOYEE, to('/apps'))).toBe('open');
  });
});

describe('the platform’s screens, which belong to no app', () => {
  const gate = createAppGate(ref(EMPLOYEE));

  it('say «No access» in the same address when the person lacks the permission of their side-menu entry', () => {
    expect(gate(to('/system', undefined, { hash: '#logs' }))).toEqual({
      name: APP_BLOCKED_ROUTE.name,
      params: { pathMatch: ['system'] },
      query: {},
      hash: '#logs',
    });
    const accountant: SessionMe = { ...EMPLOYEE, permissions: ['base.view_home'] };
    expect(gateVerdict(accountant, to('/files'))).toBe('no-access');
    expect(gateVerdict({ ...EMPLOYEE, permissions: [] }, to('/employees/42'))).toBe('no-access');
  });

  it('open with that permission, or with every permission', () => {
    expect(gateVerdict(EMPLOYEE, to('/files'))).toBe('open');
    expect(gateVerdict(EMPLOYEE, to('/employees/42'))).toBe('open');
    expect(gateVerdict({ ...EMPLOYEE, permissions: ['base.administer_hub'] }, to('/system'))).toBe('open');
    expect(gateVerdict({ ...EMPLOYEE, permissions: ['*'] }, to('/system'))).toBe('open');
  });

  it('let the gate’s own page through in the address it stopped, or the guard would send there again for ever', () => {
    expect(gate(to('/system', undefined, { name: APP_BLOCKED_ROUTE.name }))).toBe(true);
  });

  it('leave open an address no side-menu entry covers, segment by segment', () => {
    const nobody: SessionMe = { ...EMPLOYEE, permissions: [] };
    expect(gateVerdict(nobody, to('/'))).toBe('open');
    expect(gateVerdict(nobody, to('/profile'))).toBe('open');
    expect(gateVerdict(nobody, to('/systems'))).toBe('open');
    expect(gateVerdict(undefined, to('/system'))).toBe('open');
  });
});
