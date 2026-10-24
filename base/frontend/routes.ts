// Routes → pages of base, and nothing else: the Home at `/` (PLAN-HUB round 2026-10-21, the old hub's
// dashboard), Apps and System (APP-BASE-4) and Settings at `/settings` (its tab in the hash, `#data`; APP-BASE-2). The
// Home is registered before the shell's grid, so it wins `/`; named apart from it (`home`), because a second route with
// the same name would replace the first. Types only: `main.ts` globs this file eagerly.
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
  // ── Data: blueprints, imports and reset (APP-BASE-2) ──
  // Settings (its tab in the hash, `#data`), and the old hub's `/import` and `/export` pages landing on Settings › Data.
  {
    path: '/settings',
    name: 'base-settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { auth: true },
  },
  { path: '/import', redirect: { path: '/settings', hash: '#data' } },
  { path: '/export', redirect: { path: '/settings', query: { data: 'export' }, hash: '#data' } },
  // ── Files (APP-BASE-8) ──
  // The business's files (BASE-G82…G86), the old hub's `/files` and the side menu's «Files»; the folder in `?folder=`.
  {
    path: '/files',
    name: 'base-files',
    component: () => import('./pages/FilesPage.vue'),
    meta: { auth: true },
  },
];

export default routes;
