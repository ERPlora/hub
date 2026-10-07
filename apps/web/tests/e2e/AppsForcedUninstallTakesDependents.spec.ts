// Regression test for ERPlora/hub#2545 — uninstalling an app other apps need takes them with it.
//
// What it pins: «My apps» names the apps that need the one being uninstalled and, once the owner
// says yes, sends `force`. The runtime used to remove only that one app and leave the ones that
// needed it installed and «Active»; on the next boot it saw them missing their base and installed
// the base again by itself. Now the dependents leave together with it (the Business Central / Odoo
// answer, workflow HUB-F29), so the dialog has to say so before the owner confirms, and after the
// yes neither app is in «My apps» nor in the runtime's list.
//
// A bench spec on the real runtime with two real modules (installed through the dev install route,
// as `TabbarWholeWords.spec.ts` does), because what is checked is the runtime's answer to the
// screen's question, not the screen alone.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const SHOTS_DIR = process.env.HUB_E2E_SHOTS_DIR ?? '';
const BASE = { id: 'e2e_base', name: 'E2E Base' };
const CHILD = { id: 'e2e_child', name: 'E2E Child' };
/** The three sizes of the fleet's UI contract (pm#529). */
const SIZES = [
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

let session: Awaited<ReturnType<typeof loginByPin>>;

function writeModule(id: string, name: string, dependsOn: string[]): string {
  const dir = join(MODULES_DIR, id);
  mkdirSync(join(dir, 'migrations', 'postgres'), { recursive: true });
  writeFileSync(
    join(dir, 'module.json'),
    JSON.stringify({
      id,
      name,
      version: '1.0.0',
      depends_on: dependsOn,
      migrations: { postgres: ['migrations/postgres/001_init.sql'] },
    }),
  );
  writeFileSync(
    join(dir, 'migrations', 'postgres', '001_init.sql'),
    `CREATE TABLE IF NOT EXISTS ${id}_row (id TEXT PRIMARY KEY, hub_id TEXT NOT NULL);`,
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

async function installedIds(): Promise<string[]> {
  const body = (await runtimeCall('get', '/api/modules?locale=es')) as { data: { id: string }[] };
  return body.data.map((m) => m.id);
}

test.beforeAll(async () => {
  expect(MODULES_DIR, 'playwright.config.ts exports the bench modules folder').not.toBe('');
  session = await loginByPin();
});

test.beforeEach(async () => {
  // Base first: the child cannot be installed without it.
  for (const m of [BASE, CHILD]) {
    if ((await installedIds()).includes(m.id)) continue;
    const dir = writeModule(m.id, m.name, m === CHILD ? [BASE.id] : []);
    await runtimeCall('post', '/api/modules/install', { dir });
  }
  expect(await installedIds()).toEqual(expect.arrayContaining([BASE.id, CHILD.id]));
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  const left = await installedIds();
  for (const m of [CHILD, BASE]) {
    if (left.includes(m.id)) await runtimeCall('post', `/api/modules/${m.id}/uninstall`);
  }
  for (const m of [CHILD, BASE]) rmSync(join(MODULES_DIR, m.id), { recursive: true, force: true });
});

/** A row of «My apps»: `.rcard` in the cards view, `.grow-data`/`.rrow` in the table and list. */
function row(page: Page, name: string) {
  return page.locator('ok-data-table').first().locator('.rcard, .grow-data, .rrow', { hasText: name }).first();
}

test.describe('uninstalling an app others need takes them with it (hub#2545)', () => {
  test.describe.configure({ mode: 'serial' });

  for (const size of SIZES) {
    test(`${size.width}x${size.height}: the dialog says they go too, and both are gone after the yes`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize(size);
      await withSession(page, session);
      await page.goto('/apps#mine');
      await expect(row(page, BASE.name)).toBeVisible();
      await expect(row(page, CHILD.name)).toBeVisible();

      await row(page, BASE.name).getByRole('button', { name: 'Desinstalar' }).click();
      const alert = page.locator('ion-alert');
      await expect(alert).toBeVisible();
      await expect(alert).toContainText(`Estas apps necesitan ${BASE.name} y también se desinstalarán:`);
      await expect(alert).toContainText(`· ${CHILD.name}`);
      await expect(alert).not.toContainText('dejarán de funcionar');
      // Wait out the enter animation: a shot taken mid-fade shows the page above the dialog.
      await expect(alert.locator('.alert-wrapper')).toHaveCSS('opacity', '1');
      const shot = `forced-uninstall-dialog-${size.width}x${size.height}.png`;
      await page.screenshot({ path: SHOTS_DIR ? join(SHOTS_DIR, shot) : testInfo.outputPath(shot) });

      await alert.getByRole('button', { name: 'Desinstalar' }).click();
      await expect(alert).toBeHidden();
      await expect(row(page, BASE.name)).toBeHidden();
      await expect(row(page, CHILD.name)).toBeHidden();
      const ids = await installedIds();
      expect(ids, 'the runtime still lists the uninstalled app').not.toContain(BASE.id);
      expect(ids, 'the app that needed it stayed installed (hub#2545)').not.toContain(CHILD.id);
      const after = `forced-uninstall-after-${size.width}x${size.height}.png`;
      await page.screenshot({ path: SHOTS_DIR ? join(SHOTS_DIR, after) : testInfo.outputPath(after) });
    });
  }
});
