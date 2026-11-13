// Routes → pages of base, and nothing else. The Home is registered before the shell's grid, so it wins `/`; it is named
// apart from it (`home`), because a second route with the same name would replace the first. Types only: `main.ts`
// globs this file eagerly.
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'base-home',
    component: () => import('./pages/HomePage.vue'),
    meta: { auth: true },
  },
  // ── Apps ───────────────
  // «My apps», with the catalogue in `#all` and `#paid`.
  {
    path: '/apps',
    name: 'base-apps',
    component: () => import('./pages/AppsPage.vue'),
    meta: { auth: true },
  },
  // System's tabs go in the address hash (`lib/system.ts`).
  {
    path: '/system',
    name: 'base-system',
    component: () => import('./pages/SystemPage.vue'),
    meta: { auth: true },
  },
  // ── The way in ───────────────
  // «Access»: where Django's `way_in` sends a browser without a session; it paints its own frame.
  {
    path: '/login',
    name: 'base-login',
    component: () => import('./pages/LoginPage.vue'),
    meta: { auth: false, chrome: false },
  },
  // «Create your PIN» after entering with the account on a till.
  {
    path: '/pin/setup',
    name: 'base-pin-setup',
    component: () => import('./pages/PinSetupPage.vue'),
    meta: { auth: true, chrome: false },
  },
  // «Switch user» over the session it replaces.
  {
    path: '/switch-user',
    name: 'base-switch-user',
    component: () => import('./pages/SwitchUserPage.vue'),
    meta: { auth: true, chrome: false },
  },
  {
    path: '/profile',
    name: 'base-profile',
    component: () => import('./pages/ProfilePage.vue'),
    meta: { auth: true },
  },
  // ── Settings: General and Data ────────────────────────────
  // Its tab in the hash; the older `/import` and `/export` pages land on Settings › Data.
  {
    path: '/settings',
    name: 'base-settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
  // ── People and permissions ───────────────
  // Employees, its tab in the hash; a person's page is for whoever runs the business.
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
  // The API's documentation, when the business shows it (Settings › General).
  {
    path: '/api-docs',
    name: 'base-api-docs',
    component: () => import('./pages/ApiDocsPage.vue'),
    meta: { auth: true },
  },
  { path: '/import', redirect: { path: '/settings', hash: '#data' } },
  { path: '/export', redirect: { path: '/settings', query: { data: 'export' }, hash: '#data' } },
  // ── Files ───────────────
  // The business's files; the open folder in `?folder=`.
  {
    path: '/files',
    name: 'base-files',
    component: () => import('./pages/FilesPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
