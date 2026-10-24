// Routes → pages of base, and nothing else: the Home at `/` (PLAN-HUB round 2026-10-21, the old hub's
// dashboard), Apps and System (APP-BASE-4), the way in (APP-BASE-3) and Settings at `/settings` (its tab in the hash:
// General, or `#data`; APP-BASE-3 and APP-BASE-2) and Employees at `/employees` (APP-BASE-5). The Home is registered before the shell's grid, so it wins `/`;
// named apart from it (`home`), because a second route with the same name would replace the first. Types only:
// `main.ts` globs this file eagerly.
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'base-home',
    component: () => import('./pages/HomePage.vue'),
    meta: { auth: true },
  },
  // ── Apps (APP-BASE-4) ──
  // The business's apps and the catalogue (BASE-G67…G74): «My apps», `#all` and `#paid`, the old hub's addresses.
  {
    path: '/apps',
    name: 'base-apps',
    component: () => import('./pages/AppsPage.vue'),
    meta: { auth: true },
  },
  // System (BASE-G81 brings its «Plan and limits»; its other sections come with the part of System).
  {
    path: '/system',
    name: 'base-system',
    component: () => import('./pages/SystemPage.vue'),
    meta: { auth: true },
  },
  // ── The way in (APP-BASE-3) ──
  // «Access» (BASE-G55…G58): where Django's `way_in` sends a browser without a session; it paints its own frame.
  {
    path: '/login',
    name: 'base-login',
    component: () => import('./pages/LoginPage.vue'),
    meta: { auth: false, chrome: false },
  },
  // «Create your PIN» after entering with the account on a till (BASE-G54).
  {
    path: '/pin/setup',
    name: 'base-pin-setup',
    component: () => import('./pages/PinSetupPage.vue'),
    meta: { auth: true, chrome: false },
  },
  // «Switch user» over the session it replaces (BASE-G60).
  {
    path: '/switch-user',
    name: 'base-switch-user',
    component: () => import('./pages/SwitchUserPage.vue'),
    meta: { auth: true, chrome: false },
  },
  // «My profile» (BASE-G125, G126).
  {
    path: '/profile',
    name: 'base-profile',
    component: () => import('./pages/ProfilePage.vue'),
    meta: { auth: true },
  },
  // ── Settings: General (APP-BASE-3) and Data (APP-BASE-2) ──
  // Its tab in the hash: General (this device, the PIN pad and the devices: BASE-G62…G66, G72, G151) or `#data`;
  // the old hub's `/import` and `/export` pages land on Settings › Data.
  {
    path: '/settings',
    name: 'base-settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
  // ── People and permissions (APP-BASE-5) ──
  // Employees: «Staff», «Roles», «API keys» and «Approvals», the tab in the hash (BASE-G11, G138…G149); a person's
  // page, for who runs the business (BASE-G10, G139, G140).
  {
    path: '/employees',
    name: 'base-employees',
    component: () => import('./pages/EmployeesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/employees/:person',
    name: 'base-person',
    component: () => import('./pages/PersonPage.vue'),
    meta: { auth: true },
  },
  { path: '/import', redirect: { path: '/settings', hash: '#data' } },
  { path: '/export', redirect: { path: '/settings', query: { data: 'export' }, hash: '#data' } },
];

export default routes;
