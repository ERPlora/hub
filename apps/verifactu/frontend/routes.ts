// Routes → pages of the verifactu app, and nothing else: menu, permissions and active apps come from the server
// (`base.session.me`). The six sections of the old module, on the paths of the menu in apps.py, and the detail of a
// record as its own page (Back returns to the list). Types only: `main.ts` globs this file eagerly and Vite hoists
// that glob above the shell's boot hooks. Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/verifactu/records', component: () => import('./pages/RecordsPage.vue'), meta: { auth: true } },
  {
    path: '/verifactu/records/:id',
    component: () => import('./pages/RecordDetailPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
  { path: '/verifactu/contingency', component: () => import('./pages/ContingencyPage.vue'), meta: { auth: true } },
  { path: '/verifactu/events', component: () => import('./pages/EventsPage.vue'), meta: { auth: true } },
  { path: '/verifactu/recovery', component: () => import('./pages/RecoveryPage.vue'), meta: { auth: true } },
  { path: '/verifactu/config', component: () => import('./pages/ConfigPage.vue'), meta: { auth: true } },
  { path: '/verifactu/settings', component: () => import('./pages/SettingsPage.vue'), meta: { auth: true } },
];

export default routes;
