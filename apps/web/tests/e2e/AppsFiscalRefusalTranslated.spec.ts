// Regression test for ERPlora/hub#2579 — the fiscal refusal of switching off or uninstalling an app
// reads in the screen's language.
//
// What it pins: when the hub refuses to switch off or uninstall an app for a fiscal reason —
// VeriFactu still owes records to the AEAT (`verifactu.unsent_records`, ADR-0202 R2) or the business
// would be left with no app filing its regime (`fiscal.no_provider_left`, ADR-0273 D5) — the notice
// in «My apps» said the runtime's English log line on a Spanish screen. Now it says the Spanish
// sentence of the catalogue, at the three sizes of the fleet's UI contract.
//
// The app is a real one, installed through the dev install route like
// `AppsForcedUninstallTakesDependents.spec.ts`. Only the runtime's ANSWER to the switch-off and the
// uninstall is replayed, word for word as the runtime writes it (`fiscal_profile.rs`,
// `plugins/verifactu/src/engine.rs`): reaching either refusal for real needs a fiscal profile gone
// live in production or VeriFactu with a pending queue, which a bench hub cannot do through its API.
// The runtime side of both refusals is pinned by its own Rust tests.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Route } from '@playwright/test';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';
import es from '../../src/i18n/locales/es';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const SHOTS_DIR = process.env.HUB_E2E_SHOTS_DIR ?? '';
const APP = { id: 'e2e_fiscal_app', name: 'E2E Fiscal App' };
/** The three sizes of the fleet's UI contract (pm#529). */
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

/**
 * The Spanish line of `runtimeErrors.<code>`, read without assuming it exists: a catalogue that lost
 * it has to fail on the screen assertion, not on an import.
 */
function spanishLine(code: string): string {
  const line = code
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], es.runtimeErrors);
  return typeof line === 'string' ? line : `<es.runtimeErrors.${code} is missing>`;
}

/** The refusals as the runtime sends them today: a stable code and an English line for the log. */
const REFUSALS = [
  {
    code: 'verifactu.unsent_records',
    engine: '3 VeriFactu record(s) have not reached the AEAT yet: send them before disabling or removing the module',
    spanish: spanishLine('verifactu.unsent_records'),
  },
  {
    code: 'fiscal.no_provider_left',
    engine:
      'this hub files under `verifactu` and this would leave it with no module fulfilling that regime: install another provider first, or close the fiscal period',
    spanish: spanishLine('fiscal.no_provider_left'),
  },
] as const;

const ACTIONS = [
  { door: 'deactivate', button: 'Activar/Desactivar', confirm: 'Desactivar' },
  { door: 'uninstall', button: 'Desinstalar', confirm: 'Desinstalar' },
] as const;

let session: Awaited<ReturnType<typeof loginByPin>>;

async function installedIds(): Promise<string[]> {
  const api = await pwRequest.newContext();
  const res = await api.get(`${RUNTIME}/api/modules?locale=es`, { headers: { 'X-Hub-Session': session.token } });
  expect(res.ok(), `list: ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { data: { id: string; status: string }[] };
  await api.dispose();
  return body.data.map((m) => m.id);
}

async function runtimePost(path: string, data: unknown = {}): Promise<void> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}${path}`, { headers: { 'X-Hub-Session': session.token }, data });
  expect(res.ok(), `${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  await api.dispose();
}

/** The runtime refuses `door` for `APP` with `code` and its English sentence: a 409, like the real one. */
async function refuse(page: Page, door: string, code: string, engine: string): Promise<void> {
  await page.route(
    (url) => url.pathname === `/api/modules/${APP.id}/${door}`,
    async (route: Route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({ ok: false, error: { code, message: engine } }),
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

test.describe('a fiscal refusal reads in the screen language (hub#2579)', () => {
  test.describe.configure({ mode: 'serial' });

  for (const size of SIZES) {
    for (const action of ACTIONS) {
      for (const refusal of REFUSALS) {
        test(`${size.width}x${size.height}: ${action.door} refused with ${refusal.code}`, async ({ page }, testInfo) => {
          await page.setViewportSize(size);
          await withSession(page, session);
          await refuse(page, action.door, refusal.code, refusal.engine);
          await page.goto('/apps#mine');
          await expect(row(page)).toBeVisible();

          await row(page).getByRole('button', { name: action.button }).click();
          const alert = page.locator('ion-alert');
          await expect(alert).toBeVisible();
          await alert.getByRole('button', { name: action.confirm, exact: true }).click();
          await expect(alert).toBeHidden();

          // The notice says the Spanish sentence, never the runtime's log line nor its code.
          const notice = page.locator('ion-toast');
          await expect(notice).toBeVisible();
          await expect(notice).toContainText(refusal.spanish);
          const shot = `fiscal-refusal-${action.door}-${refusal.code}-${size.width}x${size.height}.png`;
          await page.screenshot({ path: SHOTS_DIR ? join(SHOTS_DIR, shot) : testInfo.outputPath(shot) });
          await expect(notice).not.toContainText(refusal.engine);
          await expect(notice).not.toContainText(refusal.code);

          // Nothing changed: the app is still installed and still «Activo».
          expect(await installedIds()).toContain(APP.id);
          await expect(row(page)).toContainText('Activo');
        });
      }
    }
  }
});
