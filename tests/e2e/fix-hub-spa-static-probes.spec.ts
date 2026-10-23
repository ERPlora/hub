// A probe for a file on a hub's host (FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE, seen by APP-WEBSITE, hub#183): a
// crawler's /robots.txt and a browser's /favicon.ico got the SPA with a 200 and a `csrftoken` cookie, so the website's
// «no cookies» broke and a crawler read HTML as the hub's robots.txt. A path that names a file and has no URL of its
// own is now a plain 404 with no cookie, whatever it accepts; a deep link of the SPA still opens the shell and sets
// the cookie its first write sends back: an item is saved through «New item» → «Save». The list in three sizes
// (FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE-390|834|1440).
// flow: ninguno — respuesta de la SPA de `base` a una ruta sin URL propia (sondeos de ficheros: `/robots.txt`, `/favicon.ico`)
import { expect, test } from '@playwright/test';

import { A, createViaPage, login, row, shot, topbarApps, uniqueName } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';

const KEY = 'FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE';
const ACCEPTS = ['*/*', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'];

test('a probe for a file gets a plain 404 with no cookie, and a deep link still opens the shell and saves', async ({
  page,
  playwright,
}) => {
  const anonymous = await playwright.request.newContext();
  for (const path of ['/robots.txt', '/favicon.ico']) {
    for (const accept of ACCEPTS) {
      const response = await anonymous.get(`${A}${path}`, { headers: { Accept: accept }, maxRedirects: 0 });
      expect(response.status(), `${path} with Accept ${accept}`).toBe(404);
      expect(response.headers()['set-cookie'], `${path} sets no cookie`).toBeUndefined();
      expect(await response.text(), `${path} is not the shell`).not.toContain('id="spa-config"');
    }
  }
  await anonymous.dispose();

  await login(page, A, '/demo/items');
  // The deep link itself must set the token again: without it the SDK's first write is refused (403).
  await page.context().clearCookies({ name: 'csrftoken' });
  const deepLink = await page.goto(`${A}/demo/items`);
  expect(deepLink?.status()).toBe(200);
  await topbarApps(page).waitFor({ state: 'attached' });
  const host = new URL(A).hostname;
  expect((await page.context().cookies(A)).some((c) => c.name === 'csrftoken' && c.domain === host)).toBe(true);

  const name = uniqueName('Probe item');
  await createViaPage(page, name);
  await expect(row(page, name)).toBeVisible();

  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await settled(page);
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
    await noHorizontalScroll(page, `${KEY} ${viewport.label}`);
    await page.screenshot({ path: shot(`${KEY}-${viewport.label}`) });
  }
});
