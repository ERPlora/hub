// @vitest-environment happy-dom
import { expect, it } from 'vitest';
import { createApp, inject } from 'vue';
import { createRouter, createWebHistory } from '@ionic/vue-router';
import { installBackClosesOverlay } from './back-closes-overlay';

const Blank = { template: '<div />' };
const settle = async () => {
  for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 5));
};

it('probe: after a Back held by an open layer, the next push is still a push for Ionic', async () => {
  const router = createRouter({
    history: createWebHistory(),
    routes: ['/a', '/b', '/c'].map((path) => ({ path, component: Blank })),
  });
  installBackClosesOverlay(router, async () => (open ? ((open = false), 'closed') : 'none'));
  let open = false;
  let nav: { getCurrentRouteInfo: () => { pathname: string; routerAction: string; routerDirection: string } } | undefined;
  const app = createApp({ render: () => null });
  app.use(router);
  app.runWithContext(() => {
    nav = inject('navManager');
  });
  await router.push('/a');
  await router.push('/b');
  open = true;
  router.back();
  await settle();
  expect(router.currentRoute.value.path).toBe('/b');
  await router.push('/c');
  await settle();
  const info = nav!.getCurrentRouteInfo();
  console.log('ROUTEINFO', JSON.stringify(info));
  expect(info.pathname).toBe('/c');
  expect(info.routerAction).toBe('push');
  expect(info.routerDirection).toBe('forward');
});
