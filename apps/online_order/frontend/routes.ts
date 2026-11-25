// Routes → pages of Online orders, and nothing else: menu, permissions and active apps come from the server
// (`base.session.me`). Its one screen is the tables' QR codes, on the path of its menu entry in apps.py. Types only:
// `main.ts` globs this file eagerly and Vite hoists that glob above the shell's boot hooks. The page is its own chunk.
import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  { path: '/online_order/qr-codes', component: () => import('./pages/QrCodesPage.vue'), meta: { auth: true } },
];

export default routes;
