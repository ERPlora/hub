// A probe for a file on a hub's host (FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE, seen by APP-WEBSITE, hub#183): a
// crawler's /robots.txt and a browser's /favicon.ico got the SPA with a 200 and a `csrftoken` cookie, so the website's
// «no cookies» broke and a crawler read HTML as the hub's robots.txt. A path that names a file and has no URL of its
// own is now a plain 404 with no cookie, whatever it accepts; a deep link of the SPA still opens the shell and sets
// the cookie its first write sends back: an item is saved through «New item» → «Save». With /favicon.ico a 404, the
// shell declares the old hub's icons (the tab's and the home screen's), static files of the Hub's own origin, with
// no CSP complaint. The list in three sizes (FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE-390|834|1440).
// flow: ninguno — respuesta de la SPA de `base` a una ruta sin URL propia (sondeos de ficheros: `/robots.txt`, `/favicon.ico`)
import { expect, test } from '@playwright/test';

import { A, createViaPage, login, row, shot, topbarApps, uniqueName } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';

const KEY = 'FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE';
const ACCEPTS = ['*/*', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'];
// The old hub's <head>: its tab icon and its home-screen icon, served from the Hub's static files.
const ICONS = [
  ['icon', '/static/base/icons/favicon.ico'],
  ['apple-touch-icon', '/static/base/icons/apple-touch-icon.png'],
] as const;

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

  const cspComplaints: string[] = [];
  page.on('console', (message) => {
    if (/content security policy/i.test(message.text())) cspComplaints.push(message.text());
  });
  await login(page, A, '/demo/items');
  // The deep link itself must set the token again: without it the SDK's first write is refused (403).
  await page.context().clearCookies({ name: 'csrftoken' });
  const deepLink = await page.goto(`${A}/demo/items`);
  expect(deepLink?.status()).toBe(200);
  await topbarApps(page).waitFor({ state: 'attached' });
  const host = new URL(A).hostname;
  expect((await page.context().cookies(A)).some((c) => c.name === 'csrftoken' && c.domain === host)).toBe(true);

  for (const [rel, href] of ICONS) {
    const link = page.locator(`head link[rel="${rel}"]`);
    await expect(link, `the shell declares its ${rel}`).toHaveAttribute('href', href);
    const icon = await page.request.get(`${A}${href}`);
    expect(icon.status(), `${href} is served`).toBe(200);
    expect(icon.headers()['content-type'], `${href} is an image`).toMatch(/^image\//);
    expect(icon.headers()['set-cookie'], `${href} sets no cookie`).toBeUndefined();
    // Headless Chrome may not fetch a tab icon: the page loads it as an image, under its own CSP (img-src).
    const shown = await page.evaluate(
      (url) =>
        new Promise<boolean>((done) => {
          const image = new Image();
          image.onload = () => done(image.naturalWidth > 0);
          image.onerror = () => done(false);
          image.src = url;
        }),
      href,
    );
    expect(shown, `${href} loads under the page's CSP`).toBe(true);
  }

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
  expect(cspComplaints, 'no CSP complaint on the page').toEqual([]);
});
