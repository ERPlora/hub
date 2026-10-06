// A settings screen whose stored values could not be read never shows factory values nor offers
// to save them (hub#2511).
//
// What it pins: the Settings screen the shell generates for any module (ADR-0082) swallowed a
// failed read of the stored values (`query(get).catch(() => null)`) and painted the schema
// defaults as if they were the business's. An administrator pressing «Save» then overwrote every
// stored setting with them — in Caja, «Enable the cash drawer» too. A failed read now shows «could
// not read» with Retry and no Save; a read refused for permission says so, without a Retry.
//
// Why a bench spec on top of the unit tests: the error state is an `ok-empty-state` with an
// `ion-button` slotted into it, and only a real browser with the real OutfitKit and Ionic tells
// whether that card and its button are actually on screen and inside it at the three widths.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import type { Route } from '@playwright/test';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { VIEWPORTS } from './viewports';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const FIXTURES = join(import.meta.dirname, 'fixtures', 'modules');
const MODULE_ID = 'e2e_settings';
const GET_QUERY = 'e2e_settings.settings.get';

interface Session {
  token: string;
  user: unknown;
}

let session: Session;

async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '000000', device_id: 'e2e-browser-device' },
  });
  expect(res.ok(), `PIN login failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  await api.dispose();
  return { token: body.token, user: body.user };
}

async function moduleCall(path: string, data?: unknown): Promise<void> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}${path}`, {
    headers: { 'X-Hub-Session': session.token },
    data: data ?? {},
  });
  expect(res.ok(), `${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  await api.dispose();
}

test.beforeAll(async () => {
  expect(MODULES_DIR, 'playwright.config.ts exports the bench modules folder').not.toBe('');
  session = await loginByPin();
  cpSync(join(FIXTURES, MODULE_ID), join(MODULES_DIR, MODULE_ID), { recursive: true });
  await moduleCall('/api/modules/install', { dir: join(MODULES_DIR, MODULE_ID) });
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  await moduleCall(`/api/modules/${MODULE_ID}/uninstall`);
  rmSync(join(MODULES_DIR, MODULE_ID), { recursive: true, force: true });
});

/** The runtime serves module assets in production; in this bench Vite does not, so the spec does. */
async function serveFixtureAssets(page: Page): Promise<void> {
  await page.route(/\/modules\/e2e_settings\//, async (route) => {
    const url = new URL(route.request().url());
    const [, , ...rest] = url.pathname.replace(/^\/modules\//, '/').split('/');
    const file = rest[0] === 'v' ? rest.slice(2) : rest; // drop `/v/<version>` (hub#935)
    const path = join(FIXTURES, MODULE_ID, ...file);
    if (!existsSync(path)) return route.fulfill({ status: 404, body: '' });
    await route.fulfill({ path });
  });
}

/**
 * Makes the read of the stored settings fail the way the issue describes, and ONLY that read:
 * every other `/api/query` of the shell goes through to the real runtime.
 */
async function failSettingsRead(page: Page, status: number, error: { code: string; message: string }): Promise<void> {
  await page.route('**/api/query', async (route: Route) => {
    const body = route.request().postDataJSON() as { name?: string } | null;
    if (body?.name !== GET_QUERY) return route.fallback();
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ ok: false, error }) });
  });
}

async function openSettings(page: Page, viewport: { width: number; height: number }): Promise<void> {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user] as const,
  );
  await serveFixtureAssets(page);
}

/** The card is on screen and whole: nothing of it hangs past the right edge of the viewport. */
async function expectInsideViewport(page: Page, testId: string, width: number): Promise<void> {
  const box = await page.getByTestId(testId).boundingBox();
  expect(box, `${testId} has a box`).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width, `${testId} overflows the ${width}px viewport`).toBeLessThanOrEqual(width + 0.5);
}

test.describe('a failed read of a module settings shows «could not read», never factory values (hub#2511)', () => {
  for (const viewport of VIEWPORTS) {
    test(`at ${viewport.width}px: Retry instead of the form, and the form once the read works`, async ({
      page,
    }, testInfo) => {
      await openSettings(page, viewport);
      await failSettingsRead(page, 503, { code: 'service_unavailable', message: 'restarting' });
      await page.goto(`/m/${MODULE_ID}/settings`);

      await expect(page.getByTestId('module-settings-error')).toBeVisible();
      await expect(page.getByTestId('module-settings-retry')).toBeVisible();
      await expect(page.getByTestId('module-settings-save')).toHaveCount(0);
      await expect(page.getByTestId('module-settings-field-track_stock')).toHaveCount(0);
      await expectInsideViewport(page, 'module-settings-error', viewport.width);
      await page.screenshot({ path: testInfo.outputPath(`read-failed-${viewport.width}x${viewport.height}.png`) });

      // The hub is back: Retry reads again and the screen becomes the form (no row yet → defaults).
      await page.unroute('**/api/query');
      await page.getByTestId('module-settings-retry').click();
      await expect(page.getByTestId('module-settings-field-track_stock')).toBeVisible();
      await expect(page.getByTestId('module-settings-save')).toBeVisible();
      await expect(page.getByTestId('module-settings-error')).toHaveCount(0);
    });

    test(`at ${viewport.width}px: a read refused for permission says so, without Retry`, async ({ page }, testInfo) => {
      await openSettings(page, viewport);
      await failSettingsRead(page, 403, { code: 'permission_denied', message: 'requires e2e_settings.configure' });
      await page.goto(`/m/${MODULE_ID}/settings`);

      await expect(page.getByTestId('module-settings-no-permission')).toBeVisible();
      await expect(page.getByTestId('module-settings-retry')).toHaveCount(0);
      await expect(page.getByTestId('module-settings-save')).toHaveCount(0);
      await expectInsideViewport(page, 'module-settings-no-permission', viewport.width);
      await page.screenshot({ path: testInfo.outputPath(`read-forbidden-${viewport.width}x${viewport.height}.png`) });
    });
  }
});
