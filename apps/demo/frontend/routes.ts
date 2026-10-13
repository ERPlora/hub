// Routes → pages of the demo app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). Types only: `main.ts` globs this file eagerly and Vite hoists that
// glob above the shell's boot hooks, so a runtime import here would load `@ionic/vue` too early.
// Each page is its own chunk (`import()`), so 300 apps do not grow the entry.
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/demo/items',
    component: () => import('./pages/ItemListPage.vue'),
    meta: { auth: true },
  },
  // Before `:id`, so «new» is never read as an item id.
  {
    path: '/demo/items/new',
    component: () => import('./pages/ItemCreatePage.vue'),
    meta: { auth: true },
  },
  {
    path: '/demo/items/:id',
    component: () => import('./pages/ItemDetailPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
  {
    path: '/demo/items/:id/edit',
    component: () => import('./pages/ItemEditPage.vue'),
    props: true,
    meta: { auth: true },
  },
];

export default routes;
