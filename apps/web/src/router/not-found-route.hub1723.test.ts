// @vitest-environment happy-dom
//
// hub#1723 — an address the hub does not have used to sit you on Inicio without a word.
//
// What QA saw on `banco-pre` (v1.1.19): typing or pasting `/sales`, `/tpv`, `/tables`,
// `/kitchen`, `/cash`, `/invoices`, `/verifactu` or `/flows` painted the Home screen, menu and
// all, exactly as if the address had been valid. The real screens live under `/m/<module>/<nav>`
// (`/m/sales/pos`), but nothing said so: whoever pasted an old link or guessed the address from
// the module's name landed somewhere else and believed they were where they asked for.
//
// The cause was one line of the table below: a catch-all that `redirect`ed everything unknown to
// `/dashboard`. A redirect is silent BY DESIGN — it rewrites the address bar, so the evidence
// that the link was wrong is destroyed on the way in.
//
// The settled answer, which is the one we take: every admin console in the market answers an
// address it does not have with a page that says so and offers one way back — Shopify admin,
// Square Dashboard, Stripe, Odoo, Business Central. Nobody redirects a bad link to the home
// screen, because the person then blames the app instead of the link.
//
// The other half of the fix is the retired routes. `/export`, `/import` and `/first-run` were
// LEANING on that catch-all (see the comment it used to carry): turning it into a 404 without
// giving them a home of their own would break three addresses that used to work, which is the
// regression this test exists to stop.
import { describe, expect, it } from 'vitest';
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router';

import { routes } from './index';

/**
 * The real table, with every screen replaced by an empty component.
 *
 * Navigation is what is under test — which record a path matches, and where a redirect lands —
 * and vue-router resolves lazy components during navigation. Stubbing them keeps this a test of
 * the route table instead of dragging the whole shell (AppPage → topbar → Ionic → OutfitKit) into
 * a unit test. Redirects are left untouched: they are the behaviour being measured.
 */
function withStubbedScreens(records: readonly RouteRecordRaw[]): RouteRecordRaw[] {
  return records.map((record) => {
    const next = { ...record } as Record<string, unknown>;
    if ('component' in record && record.component) next.component = { template: '<div />' };
    if ('children' in record && record.children) {
      next.children = withStubbedScreens(record.children as RouteRecordRaw[]);
    }
    return next as unknown as RouteRecordRaw;
  });
}

function freshRouter() {
  return createRouter({ history: createMemoryHistory(), routes: withStubbedScreens(routes) });
}

/** Every address QA typed in the report, plus the module-shaped guesses it lists. */
const ADDRESSES_THE_HUB_DOES_NOT_HAVE = [
  '/sales',
  '/tpv',
  '/pos',
  '/tables',
  '/kitchen',
  '/cash',
  '/cash-register',
  '/inventory',
  '/reservations',
  '/invoices',
  '/verifactu',
  '/flows',
  '/sales/pos',
  '/tables/floor',
  '/register',
];

describe('an address the hub does not have says so (hub#1723)', () => {
  it.each(ADDRESSES_THE_HUB_DOES_NOT_HAVE)(
    'lands %s on the 404 screen instead of painting Inicio',
    async (address) => {
      const router = freshRouter();
      await router.push(address);

      expect(
        router.currentRoute.value.name,
        `${address} still resolves to another screen instead of the 404`,
      ).toBe('not-found');
    },
  );

  it('keeps the address that was asked for, so the wrong link stays visible', async () => {
    const router = freshRouter();
    await router.push('/tpv');

    // A redirect rewrites the bar to `/dashboard` and the evidence of the bad link is gone with
    // it. Whoever pasted the link has to be able to read it back and see their typo.
    expect(router.currentRoute.value.path).toBe('/tpv');
    expect(router.currentRoute.value.fullPath).toBe('/tpv');
  });

  it('asks for a session like every other screen of the hub', async () => {
    const notFound = routes.find((r) => r.name === 'not-found');
    // Without this, a stranger with a bad link gets the hub's own chrome instead of the login
    // screen the very same address gives them today.
    expect(notFound?.meta?.auth).toBe(true);
  });

  // The control: this test discriminates only if the addresses that DO exist still resolve to
  // their own screen. A table where everything 404s would pass the block above and break the hub.
  it.each([
    ['/dashboard', 'dashboard'],
    ['/settings', 'settings'],
    ['/apps', 'apps'],
    ['/employees', 'employees'],
    ['/m/sales/pos', 'module'],
    ['/m/inventory', 'module'],
  ])('still opens %s, which does exist', async (address, name) => {
    const router = freshRouter();
    await router.push(address);

    expect(router.currentRoute.value.name).toBe(name);
  });

  it('sends /marketplace to /apps, as it already did', async () => {
    const router = freshRouter();
    await router.push('/marketplace');

    expect(router.currentRoute.value.name).toBe('apps');
  });
});

describe('the addresses that were retired keep working (hub#1723)', () => {
  // These three were relying on the old catch-all. `/export` and `/import` were the pages that
  // ADR-0113/0116 moved INTO Ajustes → Datos, so that tab is where they belong — not Inicio,
  // which is merely where the catch-all happened to dump them.
  it.each(['/export', '/import'])('takes the retired %s to Ajustes → Datos', async (address) => {
    const router = freshRouter();
    await router.push(address);

    expect(router.currentRoute.value.name).toBe('settings');
    expect(router.currentRoute.value.hash).toBe('#data');
  });

  it('takes the retired /first-run to Inicio, where setting up lives now', async () => {
    const router = freshRouter();
    await router.push('/first-run');

    expect(router.currentRoute.value.name).toBe('dashboard');
  });
});
