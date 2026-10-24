// PoC §8.7 (CSP, zero violations), §8.11 (OpenAPI ↔ list), §8.13 (no Iconify requests) and part of
// §8.4 (list → detail → back): the real login on `a`, the shell with the old hub's side menu and its
// topbar (⠿ apps; Back on a detail only, PLAN-MIGRATIONS §16), the empty state.
import { expect, test } from '@playwright/test';

import {
  A,
  api,
  clearItems,
  collectProblems,
  createItem,
  iconStates,
  listReady,
  login,
  openApps,
  record,
  rowNames,
  rowOf,
  shot,
  shown,
  uniqueName,
} from './helpers';

const ICONIFY_HOSTS = /iconify\.design|simplesvg\.com|unisvg\.com/;

test('login on a: shell, topbar with Demo among the apps, empty state, CSP header and zero violations', async ({ page, context }) => {
  const problems = await collectProblems(page);
  const iconifyRequests: string[] = [];
  const iconFetches: string[] = [];
  page.on('request', (req) => {
    if (ICONIFY_HOSTS.test(req.url())) iconifyRequests.push(req.url());
    if (req.url().includes('%3Csvg')) iconFetches.push(req.url().slice(0, 80));
  });

  await login(page, A);
  const deleted = await clearItems(context, A);
  const response = await page.goto('/demo/items');
  const csp = response?.headers()['content-security-policy'] ?? '';

  await expect(page.locator('ion-app')).toHaveCount(1);
  // The old hub's side menu (PLAN-MIGRATIONS §16), pinned at this width: the platform's entries whose
  // screen exists (Home, Apps and System today: APP-BASE-4; Settings: APP-BASE-3), never an app; the apps are the
  // topbar's sheet.
  await expect(page.locator('ion-menu.dash-menu')).toBeVisible();
  await expect(page.locator('ion-menu.dash-menu ion-item.nav-item')).toHaveText([
    /^\s*Home\s*$/,
    /^\s*Files\s*$/,
    /^\s*Apps\s*$/,
    /^\s*System\s*$/,
    /^\s*Settings\s*$/,
  ]);
  await listReady(page);
  const apps = await openApps(page);
  await expect(apps.locator('[data-testid=apps-launcher-app]', { hasText: 'Demo' })).toBeVisible();
  await apps.locator('[data-testid=apps-launcher-close]').click();
  await expect(apps).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=demo-items-empty]')).toBeVisible();
  await page.waitForTimeout(1000); // icons load when visible
  const listIcons = await iconStates(page);
  await page.screenshot({ path: shot('01-shell-empty-1280') });

  // The «New item» page and a detail page also go through the CSP (ion-input, ion-select, ion-icon).
  await shown(page).locator('[data-testid=demo-items-add]').click();
  await expect(page).toHaveURL(/\/demo\/items\/new$/);
  await expect(shown(page).locator('[data-testid=demo-form-name]')).toBeVisible();
  await page.screenshot({ path: shot('01-new-item-page') });
  await shown(page).locator('[data-testid=topbar-back]').click();
  await expect(page).toHaveURL(/\/demo\/items$/);
  const item = await createItem(context, A, uniqueName('CSP probe'));
  await page.goto(`/demo/items/${item.id}`);
  await expect(page.locator('[data-testid=demo-detail-status]')).toBeVisible();
  await page.waitForTimeout(1500); // late errors (lazy chunks, icons)

  const found = await problems();
  record('01-login-and-shell', {
    deletedBeforeStart: deleted,
    cspHeader: csp,
    requireTrustedTypes: csp.includes('require-trusted-types-for'),
    cspViolations: found.csp,
    consoleErrors: found.console,
    pageErrors: found.page,
    iconifyRequests,
    iconFetchesToOwnServer: iconFetches,
    listIcons,
    consoleWarnings: found.warnings,
  });

  expect(csp).toMatch(/script-src [^;]*'nonce-[A-Za-z0-9_-]+'/);
  expect(csp).toContain("'strict-dynamic'");
  expect(csp).toMatch(/connect-src 'self' ipc: http:\/\/ipc\.localhost/);
  expect(csp).toContain('trusted-types default');
  expect(found.csp).toEqual([]);
  expect(found.console).toEqual([]);
  expect(found.page).toEqual([]);
  expect(iconifyRequests).toEqual([]);
  // §8.13: every ion-icon paints its SVG from the baked registry, with no request at all.
  expect.soft(listIcons.filter((i) => !i.painted), 'ion-icons left empty').toEqual([]);
  expect.soft(iconFetches, 'icon SVG fetched as a URL from our own server').toEqual([]);
});

test('OpenAPI lists the seven demo operations by name and the API returns what the list paints', async ({ page, context }) => {
  await login(page, A);
  const spec = await context.request.get(`${A}/api/openapi.json`);
  expect(spec.status()).toBe(200);
  const doc = (await spec.json()) as { paths: Record<string, Record<string, { operationId?: string }>> };
  const demoOps = Object.entries(doc.paths)
    .filter(([path]) => path.includes('/demo/'))
    .flatMap(([, methods]) => Object.values(methods).map((op) => op.operationId))
    .sort();
  const docs = await context.request.get(`${A}/api/docs`);

  await createItem(context, A, uniqueName('OpenAPI probe'));
  await page.goto('/demo/items');
  await listReady(page);
  const painted = await rowNames(page);
  const listed = await api<{ rows: { name: string }[] }>(context, A, 'GET', '/demo/items?limit=50');
  record('11-openapi', { demoOperationIds: demoOps, docsStatus: docs.status(), painted, apiNames: listed.data.rows.map((r) => r.name) });

  expect(demoOps).toEqual([
    'demo.item.add_line',
    'demo.item.create',
    'demo.item.delete',
    'demo.item.detail',
    'demo.item.list',
    'demo.item.stats',
    'demo.item.update',
  ]);
  expect(docs.status()).toBe(200);
  expect(painted).toEqual(listed.data.rows.map((r) => r.name));
});

test('IonRouterOutlet: list → detail → topbar back', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Nav probe'));
  await page.goto('/demo/items');
  await listReady(page);
  const marker = await page.evaluate(() => ((window as unknown as { __nav: number }).__nav = Date.now()));

  await rowOf(page, item.id).click();
  await expect(page).toHaveURL(new RegExp(`/demo/items/${item.id}$`));
  await expect(shown(page).locator('[data-testid=demo-detail-status]')).toBeVisible();
  // During the forward transition both pages are in the outlet; the list stays (hidden) behind.
  const pagesInOutlet = await page.locator('ion-router-outlet > .ion-page').count();
  await page.screenshot({ path: shot('04-detail-from-list') });

  await shown(page).locator('[data-testid=topbar-back]').click();
  await expect(page).toHaveURL(/\/demo\/items$/);
  await listReady(page);
  const sameDocument = await page.evaluate(() => (window as unknown as { __nav?: number }).__nav);
  record('04-navigation', { pagesInOutletOnDetail: pagesInOutlet, sameDocumentAfterBack: sameDocument === marker });
  expect(sameDocument).toBe(marker);
  expect(pagesInOutlet).toBe(2);
});
