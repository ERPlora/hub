// Routes → pages of the customer app, and nothing else: menu, permissions and active apps come from
// the server (`base.session.me`). Types only: `main.ts` globs this file eagerly and Vite hoists that
// glob above the shell's boot hooks, so a runtime import here would load `@ionic/vue` too early.
// Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/customer/customers',
    component: () => import('./pages/CustomerListPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/customer/customers/:id',
    component: () => import('./pages/CustomerDetailPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
  {
    path: '/customer/groups',
    component: () => import('./pages/GroupListPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/customer/tags',
    component: () => import('./pages/TagListPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/customer/fields',
    component: () => import('./pages/FieldListPage.vue'),
    meta: { auth: true },
  },
  // The till's customer search lives in the Sales app's screen (WORKBOOK «Buscador de cliente del
  // TPV»); until Sales exists, this page shows it on the dev server only (its e2e drives it).
  ...(import.meta.env.DEV
    ? [
        {
          path: '/customer/preview/customer-search',
          component: () => import('./pages/CustomerSearchPreviewPage.vue'),
          meta: { auth: true },
        },
      ]
    : []),
];

export default routes;
