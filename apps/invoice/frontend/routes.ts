// Routes → pages of the invoice app, and nothing else: menu, permissions and active apps come from the
// server (`base.session.me`). The sections of the old module (Invoices, Series) plus the Issuer, on the
// paths of the menu in apps.py, and the detail of an invoice as its own page (Back returns to the list).
// Types only: `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks.
// Each page is its own chunk (`import()`).
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/invoice/invoices',
    component: () => import('./pages/InvoicesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/invoice/invoices/:id',
    component: () => import('./pages/InvoiceDetailPage.vue'),
    // Ionic keeps one view per URL and hands it its params once: no reactive route to go stale.
    props: true,
    meta: { auth: true },
  },
  {
    path: '/invoice/series',
    component: () => import('./pages/SeriesPage.vue'),
    meta: { auth: true },
  },
  {
    path: '/invoice/issuer',
    component: () => import('./pages/IssuerPage.vue'),
    meta: { auth: true },
  },
  // The page a customer opens with the code on her ticket, without a session; base's public door serves its HTML.
  {
    path: '/p/:slug/invoice/:code',
    component: () => import('./pages/PublicInvoicePage.vue'),
    meta: { auth: false, chrome: false },
  },
];

export default routes;
