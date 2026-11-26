// Routes → pages of Online orders, and nothing else: menu, permissions and active apps come from the server
// (`base.session.me`). Its one screen is the tables' QR codes, on the path of its menu entry in apps.py; the table's
// page, which its QR opens without a session, is base's public door's (`/p/<slug>/order/<code>`). Types only: `main.ts`
// globs this file eagerly and Vite hoists that glob above the shell's boot hooks. Each page is its own chunk.
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/online_order/qr-codes', component: () => import('./pages/QrCodesPage.vue'), meta: { auth: true } },
  {
    path: '/p/:slug/order/:code',
    component: () => import('./pages/TableMenuPage.vue'),
    meta: { auth: false, chrome: false },
  },
];

export default routes;
