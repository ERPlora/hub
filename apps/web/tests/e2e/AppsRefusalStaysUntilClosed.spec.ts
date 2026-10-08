// Regression test for ERPlora/hub#2594 — in «My apps», the reason the hub gave for refusing to switch
// off, uninstall or update an app went away on its own after 2.5 s, before anyone could read it.
//
// What it pins, in the real browser at the three sizes of the fleet's UI contract: after the hub
// refuses, the red notice is still on screen well past those 2.5 s, and its «Cerrar» button takes it
// away. The app is a real one, installed through the dev install route like
// `AppsFiscalRefusalTranslated.spec.ts`; only the runtime's ANSWER to the action is replayed —
// reaching the fiscal refusal or a blocked update for real needs a fiscal profile gone live or a paid
// app on erplora.com, which a bench hub cannot do through its API.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Route } from '@playwright/test';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';
import es from '../../src/i18n/locales/es';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const SHOTS_DIR = process.env.HUB_E2E_SHOTS_DIR ?? '';
const APP = { id: 'e2e_refusal_app', name: 'E2E Refusal App' };
/** The three sizes of the fleet's UI contract (pm#529). */
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;
/** The old notice lasted 2500 ms: this is comfortably past it. */
const PAST_THE_OLD_TIMEOUT_MS = 3500;

const fill = (s: string, params: Record<string, string>) =>
  Object.entries(params).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(v), s);

/** Each refused action: how the runtime answers, how the row asks, and what the notice must say. */
const ACTIONS = [
  {
    door: 'deactivate',
    button: es.apps.actionToggle,
    confirm: es.apps.toggleOffConfirm,
    // As `plugins/verifactu/src/engine.rs` writes it, with its stable code.
    answer: {
      status: 409,
      body: {
        ok: false,
        error: {
          code: 'verifactu.unsent_records',
          message: '3 VeriFactu record(s) have not reached the AEAT yet: send them before disabling or removing the module',
        },
      },
    },
    says: es.runtimeErrors.verifactu.unsent_records,
  },
  {
    door: 'uninstall',
    button: es.apps.actionUninstall,
    confirm: es.apps.uninstallConfirm,
    // As `fiscal_profile.rs` writes it.
    answer: {
      status: 409,
      body: {
        ok: false,
        error: {
          code: 'fiscal.no_provider_left',
          message:
            'this hub files under `verifactu` and this would leave it with no module fulfilling that regime: install another provider first, or close the fiscal period',
        },
      },
    },
    says: es.runtimeErrors.fiscal.no_provider_left,
  },
  {
    door: 'update',
    button: es.apps.actionUpdate,
    confirm: null,
    // The new version needs a paid app the hub has not subscribed to (ADR-0060).
    answer: {
      status: 409,
      body: { ok: false, code: 'install_blocked', error: 'blocked', blocked_on: ['payroll'], purchase: [] },
    },
    says: fill(es.apps.updateBlocked, { name: APP.name, missing: 'payroll' }),
  },
  {
    door: 'update',
    label: 'update ran out of time',
    button: es.apps.actionUpdate,
    confirm: null,
    // hub#2556: the download of the new version trickled past the ceiling, the runtime put the
    // previous version back and answers 200 with the warning (`module_api.rs` `update_module`).
    answer: {
      status: 200,
      body: {
        ok: true,
        data: { module_id: APP.id, version: '1.0.0', updated: false },
        warning: {
          code: 'module.update_failed_kept_previous',
          cause: 'install_cloud_timeout',
          message: 'the cloud did not answer in time',
        },
      },
    },
    says: fill(es.apps.updateTimedOut, { name: APP.name }),
    retry: es.apps.installRetry,
  },
] as const;

let session: Awaited<ReturnType<typeof loginByPin>>;

async function installedIds(): Promise<string[]> {
  const api = await pwRequest.newContext();
  const res = await api.get(`${RUNTIME}/api/modules?locale=es`, { headers: { 'X-Hub-Session': session.token } });
  expect(res.ok(), `list: ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { data: { id: string }[] };
  await api.dispose();
  return body.data.map((m) => m.id);
}

async function runtimePost(path: string, data: unknown = {}): Promise<void> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}${path}`, { headers: { 'X-Hub-Session': session.token }, data });
  expect(res.ok(), `${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  await api.dispose();
}

/** The runtime refuses `door` for `APP` with `answer`; for an update, it first offers one. */
async function refuse(page: Page, action: (typeof ACTIONS)[number]): Promise<void> {
  if (action.door === 'update') {
    await page.route(
      (url) => url.pathname === '/api/modules/updates',
      (route: Route) =>
        route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            data: [
              { module_id: APP.id, installed: '1.0.0', latest: '1.0.1', update_available: true, pinned: null, checked: true },
            ],
          }),
        }),
    );
    await page.route(
      (url) => url.pathname === `/api/modules/${APP.id}/versions`,
      (route: Route) =>
        route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            data: { module_id: APP.id, installed: '1.0.0', latest: '1.0.1', versions: ['1.0.1'] },
          }),
        }),
    );
  }
  await page.route(
    (url) => url.pathname === `/api/modules/${APP.id}/${action.door}`,
    async (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      await route.fulfill({
        status: action.answer.status,
        contentType: 'application/json',
        body: JSON.stringify(action.answer.body),
      });
    },
  );
}

/** A row of «My apps»: `.rcard` in the cards view, `.grow-data`/`.rrow` in the table and list. */
function row(page: Page) {
  return page.locator('ok-data-table').first().locator('.rcard, .grow-data, .rrow', { hasText: APP.name }).first();
}

test.beforeAll(async () => {
  expect(MODULES_DIR, 'playwright.config.ts exports the bench modules folder').not.toBe('');
  session = await loginByPin();
  if ((await installedIds()).includes(APP.id)) return;
  const dir = join(MODULES_DIR, APP.id);
  mkdirSync(join(dir, 'migrations', 'postgres'), { recursive: true });
  writeFileSync(
    join(dir, 'module.json'),
    JSON.stringify({
      id: APP.id,
      name: APP.name,
      version: '1.0.0',
      migrations: { postgres: ['migrations/postgres/001_init.sql'] },
    }),
  );
  writeFileSync(
    join(dir, 'migrations', 'postgres', '001_init.sql'),
    `CREATE TABLE IF NOT EXISTS ${APP.id}_row (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);`,
  );
  await runtimePost('/api/modules/install', { dir });
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  if ((await installedIds()).includes(APP.id)) await runtimePost(`/api/modules/${APP.id}/uninstall`);
  rmSync(join(MODULES_DIR, APP.id), { recursive: true, force: true });
});

test.describe('a refusal in «My apps» stays until it is closed (hub#2594)', () => {
  test.describe.configure({ mode: 'serial' });

  for (const size of SIZES) {
    for (const action of ACTIONS) {
      const label = 'label' in action ? action.label : `${action.door} refused`;
      test(`${size.width}x${size.height}: ${label}`, async ({ page }, testInfo) => {
        await page.setViewportSize(size);
        await withSession(page, session);
        await refuse(page, action);
        await page.goto('/apps#mine');
        await expect(row(page)).toBeVisible();

        const button = row(page).getByRole('button', { name: action.button });
        await expect(button).toBeVisible();
        await button.click();
        if (action.confirm) {
          const alert = page.locator('ion-alert');
          await expect(alert).toBeVisible();
          await alert.getByRole('button', { name: action.confirm, exact: true }).click();
          await expect(alert).toBeHidden();
        }

        const notice = page.locator('ion-toast');
        await expect(notice).toBeVisible();
        await expect(notice).toContainText(action.says);

        // The bug: at 2.5 s it was gone. It has to still be there to be read.
        await page.waitForTimeout(PAST_THE_OLD_TIMEOUT_MS);
        await expect(notice).toBeVisible();
        await expect(notice).toContainText(action.says);
        if ('retry' in action) {
          // A slow erplora.com is usually a passing thing: the notice offers to try again.
          const retry = notice.getByRole('button', { name: action.retry, exact: true });
          await expect(retry).toBeVisible();
          await expect(retry).toBeEnabled();
        }
        // The click on the row left the pointer where the notice now is: take it away so the
        // picture shows the notice at rest, not a hovered button (in `ios` mode a hovered toast
        // button fades to 0.6 and back with a transition).
        await page.mouse.move(0, 0);
        await page.waitForTimeout(400);
        const box = await notice.boundingBox();
        expect(box, 'the notice is on screen').not.toBeNull();
        expect(box!.x >= 0 && box!.x + box!.width <= size.width, 'the notice fits the window width').toBe(true);
        const slug = label.replace(/\s+/g, '-');
        const shot = `apps-refusal-${slug}-${size.width}x${size.height}.png`;
        await page.screenshot({ path: SHOTS_DIR ? join(SHOTS_DIR, shot) : testInfo.outputPath(shot) });

        // …and «Cerrar» takes it away.
        await notice.getByRole('button', { name: es.apps.noticeClose, exact: true }).click();
        await expect(notice).toBeHidden();

        // Nothing changed: the app is still installed.
        expect(await installedIds()).toContain(APP.id);
      });
    }
  }
});
