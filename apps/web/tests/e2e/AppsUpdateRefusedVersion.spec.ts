// Regression test for ERPlora/hub#2546 — an explicit version the hub does not move to is refused.
//
// What it pins: «Update» in «My apps» sends the version the owner picked (or the only one offered)
// to the runtime, and the runtime used to install it as-is — even one behind the installed version,
// or around support's pin. Now the runtime holds an explicit version to the version list's rule
// (HUB-F23/HUB-F24) and answers `update_version_not_offered`; the screen tells the owner, in their
// language, that nothing changed, and the app stays on the version it had.
//
// The bench has no erplora.com, so the two things only erplora.com knows are answered here: which
// apps have something new (`/api/modules/updates`) and which versions can be picked
// (`/api/modules/:id/versions`, answered with an OLDER one — a list gone stale). The update itself
// goes to the REAL runtime, with a real module installed through the dev install route: the
// refusal on screen is the runtime's, not a fixture's.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const SHOTS_DIR = process.env.HUB_E2E_SHOTS_DIR ?? '';
const APP = { id: 'e2e_versioned', name: 'E2E Versioned', version: '1.0.0' };
const OLDER = '0.5.0';
/** The three sizes of the fleet's UI contract (pm#529). */
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

let session: Awaited<ReturnType<typeof loginByPin>>;

function writeModule(): string {
  const dir = join(MODULES_DIR, APP.id);
  mkdirSync(join(dir, 'migrations', 'postgres'), { recursive: true });
  writeFileSync(
    join(dir, 'module.json'),
    JSON.stringify({
      id: APP.id,
      name: APP.name,
      version: APP.version,
      migrations: { postgres: ['migrations/postgres/001_init.sql'] },
    }),
  );
  writeFileSync(
    join(dir, 'migrations', 'postgres', '001_init.sql'),
    `CREATE TABLE IF NOT EXISTS ${APP.id}_row (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);`,
  );
  return dir;
}

async function runtimeCall(method: 'get' | 'post', path: string, data?: unknown): Promise<unknown> {
  const api = await pwRequest.newContext();
  const res = await api[method](`${RUNTIME}${path}`, {
    headers: { 'X-Hub-Session': session.token },
    ...(method === 'post' ? { data: data ?? {} } : {}),
  });
  expect(res.ok(), `${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  await api.dispose();
  return body;
}

async function installed(): Promise<{ id: string; version: string }[]> {
  const body = (await runtimeCall('get', '/api/modules?locale=es')) as {
    data: { id: string; version: string }[];
  };
  return body.data;
}

test.beforeAll(async () => {
  expect(MODULES_DIR, 'playwright.config.ts exports the bench modules folder').not.toBe('');
  session = await loginByPin();
  if (!(await installed()).some((m) => m.id === APP.id)) {
    await runtimeCall('post', '/api/modules/install', { dir: writeModule() });
  }
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  if ((await installed()).some((m) => m.id === APP.id)) {
    await runtimeCall('post', `/api/modules/${APP.id}/uninstall`);
  }
  rmSync(join(MODULES_DIR, APP.id), { recursive: true, force: true });
});

/** What only erplora.com knows, answered here; the update POST is NOT routed. */
async function answerWhatTheCloudWould(page: Page): Promise<void> {
  await page.route(/\/api\/modules\/updates/, (r) =>
    r.fulfill({
      json: {
        ok: true,
        data: [
          {
            module_id: APP.id,
            installed: APP.version,
            latest: OLDER,
            update_available: true,
            pinned: null,
            latest_min_erplora_version: null,
            checked: true,
          },
        ],
      },
    }),
  );
  await page.route(new RegExp(`/api/modules/${APP.id}/versions`), (r) =>
    r.fulfill({
      json: { ok: true, data: { module_id: APP.id, installed: APP.version, latest: OLDER, versions: [OLDER] } },
    }),
  );
}

/** A row of «My apps»: `.rcard` in the cards view, `.grow-data`/`.rrow` in the table and list. */
function row(page: Page) {
  return page.locator('ok-data-table').first().locator('.rcard, .grow-data, .rrow', { hasText: APP.name }).first();
}

test.describe('an older version asked for by «Update» is refused by the runtime (hub#2546)', () => {
  test.describe.configure({ mode: 'serial' });

  for (const size of SIZES) {
    test(`${size.width}x${size.height}: the refusal is said and the app keeps its version`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize(size);
      await answerWhatTheCloudWould(page);
      await withSession(page, session);
      await page.goto('/apps#mine');
      await expect(row(page)).toBeVisible();

      const update = page.waitForResponse((r) => r.url().endsWith(`/api/modules/${APP.id}/update`));
      await row(page).getByRole('button', { name: 'Actualizar' }).click();
      const response = await update;
      expect(response.status()).toBe(409);
      expect((await response.json()).code).toBe('update_version_not_offered');

      const toast = page.locator('ion-toast').filter({ hasText: 'Esta app no se puede pasar a esa versión' });
      await expect(toast).toBeVisible();
      // The danger toast stays until «Cerrar» is pressed (hub#2594); the shot is taken as soon as it is on screen.
      const shot = `update-refused-version-${size.width}x${size.height}.png`;
      await page.screenshot({ path: SHOTS_DIR ? join(SHOTS_DIR, shot) : testInfo.outputPath(shot) });

      const after = (await installed()).find((m) => m.id === APP.id);
      expect(after?.version, 'the runtime moved the app to the version it refused (hub#2546)').toBe(APP.version);
    });
  }
});
