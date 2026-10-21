// flow: KITCHEN-F01 — hub#2281: a failure the server did not word reaches the screen as a sentence in the
// person's language that says what happened and what to do, never the SDK's English («Unexpected response
// (HTTP 502)», «Network error (Failed to fetch)»). Seen in Kitchen › Stations › «Add station»: saving answers a
// proxy's 502 HTML page, or never gets an answer, and the panel says why in Spanish, as Ioan sees it, at 390, 834
// and 1440, keeping what was typed. The request is stopped in the browser (`page.route`), so nothing is created.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, shot, shown } from './helpers';
import { stamp } from './sale-helpers';

const NAME = `E2E K2281 ${stamp()}`;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
// The SDK's catalogue (`@erplora/ui` `src/sdk/locales/es.json`), letter by letter.
const UNEXPECTED = 'No se pudo completar la operación. Vuelve a intentarlo en unos segundos y avisa a un administrador si sigue pasando.';
const NETWORK = 'No se pudo conectar con el servidor. Revisa tu conexión y vuelve a intentarlo en unos segundos.';

/** The owner on `a` in Spanish: the Hub's language cookie, as the sign-in sets it from the account. */
async function spanishOwner(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/kitchen/stations');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/kitchen/stations`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return { context, page };
}

/** Saving a station (POST `/api/kitchen/stations`) gets `answer` instead of reaching the Hub. */
async function breakSaving(page: Page, answer: 'bad-gateway' | 'no-network'): Promise<void> {
  await page.unroute('**/api/kitchen/stations');
  await page.route('**/api/kitchen/stations', (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    if (answer === 'no-network') return route.abort('internetdisconnected');
    return route.fulfill({ status: 502, contentType: 'text/html', body: '<html><body><h1>502 Bad Gateway</h1><hr>nginx</body></html>' });
  });
}

for (const size of SIZES) {
  test(`hub#2281 at ${size.label}: «Add station» says in Spanish what happened and what to do when the server did not word it`, async ({ browser }) => {
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height });
    try {
      await shown(page).locator('[data-testid=kitchen-stations-primary-action]').click();
      const form = page.locator('ion-modal[data-testid=kitchen-station-form]');
      await expect(form).toBeVisible();
      const name = form.locator('[data-testid=kitchen-station-form-name] input');
      await name.fill(NAME);
      const error = form.locator('[data-testid=kitchen-station-form-error]');

      // A 502 with a proxy's HTML page: not the Hub's envelope.
      await breakSaving(page, 'bad-gateway');
      await form.locator('[data-testid=kitchen-station-form-submit]').click();
      await expect(error).toHaveText(UNEXPECTED);
      await expect(error).not.toContainText('Unexpected response');
      await expect(error).not.toContainText('HTTP');
      await expect(form).toBeVisible();
      await expect(name).toHaveValue(NAME);
      await error.scrollIntoViewIfNeeded();
      await expect(error).toBeInViewport();
      await page.screenshot({ path: shot(`CLOSE-KITCHEN-hub2281-502-${size.label}`) });

      // A request that never gets an answer.
      await breakSaving(page, 'no-network');
      await form.locator('[data-testid=kitchen-station-form-submit]').click();
      await expect(error).toHaveText(NETWORK);
      await expect(error).not.toContainText('Network error');
      await expect(name).toHaveValue(NAME);
      await page.screenshot({ path: shot(`CLOSE-KITCHEN-hub2281-network-${size.label}`) });

      // Nothing reached the Hub: no station with that name.
      await page.unroute('**/api/kitchen/stations');
      const list = await api<{ rows: { name: string }[] }>(context, A, 'GET', `/kitchen/stations?search=${encodeURIComponent(NAME)}&limit=10`);
      expect(list.status).toBe(200);
      expect(list.data.rows.filter((row) => row.name === NAME)).toEqual([]);
    } finally {
      await context.close();
    }
  });
}
