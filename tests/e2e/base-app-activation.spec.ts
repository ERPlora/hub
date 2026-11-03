// Turning an app on and off, and the plan's limit of apps (PLAN-HUB §9, ronda 2026-10-24b; BASE-F18, F23, F24), in the
// three viewports, as the owner of hub `a`: Apps counts the apps the business chose against the plan's `max_apps`
// (Gratis, 20); «Turn off» Tasks asks with its name and, confirmed, takes it out of «My apps» and of the topbar's «My
// apps» (the menu), and its screens say why they do not open; «Turn on» brings it back. With 20 chosen apps on, the
// 21st is refused with the plan's notice and «Upgrade plan» (erplora.com's plans). Each flow leaves its capture
// `APP-BASE-ACTIVATION-<step>-<width>`. The photo is sent the way the SaaS sends it (`PUT /internal/hubs/{id}/state`,
// signed); `a`'s photo is put back after the run and its rows of `base_appactivation` are put back before and after
// each test to every app on with the roots chosen, as `seed_local_hubs` leaves the local hubs (a business is born with
// every app off, PLAN-HUB round 2026-10-27: `a` stands for a hub of before, which kept them on).
// In Spanish, the flows of FIX-HUB-BASE-APP-ACTIVATION-WORKBOOK-AND-FLOWS, each with its capture
// `FIX-HUB-BASE-APP-ACTIVATION-<flow>-<width>`: «Activar» an app the business does not use (BASE-F18); «Desactivar»
// Reservations names Tables, which came along only with it, and «Activar» brings both back, naming it (BASE-F19,
// BASE-F23, BASE-F24); Tables while Reservations needs it is refused with what to turn off first, in a notice that
// stays until it is closed (BASE-F25, hub#2594); and VeriFactu, with a ticket whose record is not in the AEAT yet,
// refuses with its own reason (BASE-F25, VERIFACTU-F32). That ticket is issued through Invoicing's API and deleted
// after the run with its record (`cleanInvoices`), the numbering given back.
// flow: BASE-F18 BASE-F19 BASE-F23 BASE-F24 BASE-F25 BASE-F26
import { execFileSync } from 'node:child_process';
import { createHmac } from 'node:crypto';

import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, HUB_DIR, hostPage, login, psql, shot, shown, untilStill } from './helpers';
import { cleanInvoices, ensureIssuer, issuedIds, snapshotSeries } from './invoice-helpers';
import { STACK } from './stack';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The copy the run keeps of `a`'s photo. */
const BACKUP = 'e2e_base_app_activation_photo_before';
/** Gratis (PLAN §32): 20 apps the business chooses. */
const GRATIS = { slug: 'free', max_users: 0, max_devices: 0, max_apps: 20 };

let hubId = '';
let version = Math.floor(Date.now() / 1000);

async function pushPhoto(plan: Record<string, unknown>): Promise<void> {
  version += 1;
  const body = JSON.stringify({ hub_id: hubId, slug: 'a', version, plan });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${hubId}/state`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** The copy the run keeps of `a`'s rows with every app on (`seed_local_hubs`). */
const ROWS = 'e2e_base_app_activation_rows';

/** `a` back to every app on, its roots chosen: the rows `seed_local_hubs` wrote, kept at the start of the run. */
const baseline = () =>
  psql(`delete from base_appactivation where host = 'a'; insert into base_appactivation select * from ${ROWS}`);

test.beforeAll(() => {
  hubId = psql("select id from base_hub where slug = 'a'");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(hubId)) {
    throw new Error(`The registry of DB_NAME=${STACK.database} has no hub a (got ${JSON.stringify(hubId)}): run node tests/e2e/database.ts.`);
  }
  version = Math.max(version, Number(psql(`select state_version from base_hub where id = '${hubId}'`)));
  psql(
    [
      `drop table if exists ${BACKUP}`,
      `create table ${BACKUP} as select id, state, state_version from base_hub where id = '${hubId}'`,
    ].join('; '),
  );
  // Every app on in `a`, whatever a run before left: its rows cleared and written again by `seed_local_hubs` (this
  // checkout's, on this run's database), then kept for `baseline`.
  psql("delete from base_appactivation where host = 'a'");
  execFileSync('uv', ['run', 'python', 'manage.py', 'seed_local_hubs'], {
    cwd: HUB_DIR,
    env: { ...process.env, DEBUG: 'True' },
    encoding: 'utf8',
  });
  psql(`drop table if exists ${ROWS}; create table ${ROWS} as select * from base_appactivation where host = 'a'`);
  expect(Number(psql(`select count(*) from ${ROWS}`)), 'seed_local_hubs wrote every app of a').toBeGreaterThan(0);
  snapshotSeries();
});

test.afterAll(() => {
  // The ticket BASE-F25 issued, with its VeriFactu record, and the numbering as the run found it.
  cleanInvoices();
  baseline();
  psql(
    [
      `update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP} b where b.id = h.id`,
      `drop table ${BACKUP}`,
      `drop table ${ROWS}`,
    ].join('; '),
  );
});

test.beforeEach(baseline);
test.afterEach(baseline);

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const appRow = (page: Page, id: string) => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

/** The list searched for `name`: the rows are paged, an app far down the list is not on screen. */
async function search(page: Page, name: string): Promise<void> {
  await testid(page, 'apps-search').locator('input').fill(name);
}

/** The capture of a step, once the screen settled and nothing scrolls sideways. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-ACTIVATION-${key}-${width}`) });
}

/** The names the topbar's «My apps» (the menu of the apps, from the session) lists now. */
async function menuApps(page: Page): Promise<string[]> {
  await testid(page, 'topbar-apps').click();
  const sheet = page.locator('[data-testid="apps-launcher"]').last();
  const tiles = sheet.locator('[data-testid="apps-launcher-app"]');
  await expect(tiles.first()).toBeVisible();
  const names = (await tiles.allInnerTexts()).map((name) => name.trim());
  await sheet.locator('[data-testid="apps-launcher-close"]').click();
  await expect(sheet).toBeHidden();
  return names;
}

async function signedIn(browser: Browser, viewport: { width: number; height: number }, next: string) {
  return hostPage(browser, A, { viewport, next });
}

/** The owner of `a` on `next`, with the Hub in Spanish (its language cookie, as the language picker leaves it). */
async function signedInSpanish(browser: Browser, viewport: { width: number; height: number }, next: string) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  // A reload, not a goto: the login already left the page on `next`, and a goto to the same address with a hash
  // would not load it again.
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return { context, page };
}

/** The toast that says `text` (one at a time: a new one closes the one on screen). */
const toast = (page: Page, text: string) => page.locator('ion-toast').filter({ hasText: text }).last();

/** The app names on screen that do not fit their cell and are cut without «…» (a long name such as «Ventas / TPV»
 *  or «Facturación» in a narrow column): each one is whole, or ends in an ellipsis. */
async function namesCutShort(page: Page): Promise<string[]> {
  return shown(page)
    .locator('[data-testid="apps-row"] .apps-name')
    .evaluateAll((names) =>
      names.flatMap((box) => {
        const text = box.lastElementChild as HTMLElement | null;
        const cell = box.closest('[role="cell"]') as HTMLElement | null;
        if (!text || !cell || !text.textContent?.trim()) return [];
        const edge = cell.getBoundingClientRect().right - parseFloat(getComputedStyle(cell).paddingRight) + 1;
        const ellipsis = getComputedStyle(text).textOverflow === 'ellipsis' && text.scrollWidth > text.clientWidth;
        const inside = text.getBoundingClientRect().right <= edge;
        return inside && (ellipsis || text.scrollWidth <= text.clientWidth + 1) ? [] : [text.textContent.trim()];
      }),
    );
}

/** Opens `path` from inside the Hub, as one of its links does: the SPA's router, no page load. */
async function openInside(page: Page, path: string): Promise<void> {
  type Mounted = { __vue_app__: { config: { globalProperties: { $router: { push: (to: string) => Promise<unknown> } } } } };
  await page.evaluate(
    (to) => (document.querySelector('#app') as unknown as Mounted).__vue_app__.config.globalProperties.$router.push(to),
    path,
  );
}

/** `a`'s row of `app` as `state:chosen`, or `none`. */
const stored = (app: string) =>
  psql(`select coalesce((select state || ':' || chosen from base_appactivation where host = 'a' and app = '${app}'), 'none')`);

test.describe.configure({ mode: 'serial' });

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F23 BASE-F24 — turn Tasks off and on again at ${width}`, async ({ browser }) => {
    await pushPhoto(GRATIS);
    const { context, page } = await signedIn(browser, viewport, '/apps');
    try {
      const listed = await api<{ apps: { id: string; path: string | null }[] }>(context, A, 'GET', '/apps');
      const tasksScreen = listed.data.apps.find((app) => app.id === 'task')?.path ?? '';
      expect(tasksScreen, 'Tasks has a screen for the owner').toBeTruthy();

      // The baseline: every app on, the roots chosen (17 with the reference app of development) of Gratis's 20.
      await expect(testid(page, 'apps-counter')).toHaveText('17 of 20 apps turned on');
      await search(page, 'Tasks');
      await expect(appRow(page, 'task')).toBeVisible();
      expect(await menuApps(page)).toContain('Tasks');
      await snap(page, 'counter', width);

      // Tasks' own screen, visited while on and left behind (as Ionic keeps the pages one came from): the gate below
      // must win over it in the same address.
      await openInside(page, tasksScreen);
      await expect(testid(page, 'task-views')).toBeVisible();
      await openInside(page, '/apps');
      await expect(testid(page, 'apps-counter')).toBeVisible();

      // BASE-F23 — «Turn off» asks with its name; confirmed, Tasks leaves «My apps» and the menu.
      await testid(page, 'apps-row-task-toggle').click();
      const confirm = page.locator('.ep-confirm-dialog').last();
      await expect(confirm).toContainText('Turn off Tasks?');
      await expect(confirm).toContainText('Nothing is deleted');
      await expect(confirm.getByRole('button', { name: 'Turn off' })).toBeInViewport({ ratio: 1 });
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-ACTIVATION-confirm-off-${width}`) });
      await confirm.getByRole('button', { name: 'Turn off' }).click();
      await expect(appRow(page, 'task')).toHaveCount(0);
      await expect(testid(page, 'apps-counter')).toHaveText('16 of 20 apps turned on');
      await expect.poll(() => menuApps(page), { message: 'the menu follows without a reload' }).not.toContain('Tasks');
      await snap(page, 'off', width);

      // Its screen says why it does not open, and its data is not touched (BASE-F26), opened from inside the Hub (as a
      // link of a notice would), left and opened again, and loaded cold (a bookmark), with no error of the page any way:
      // the gate's page is mounted in Tasks' address, and the outlet looked it up by that address, found none and read
      // `ionPageElement` of nothing (the page that was on screen stayed there, inside the Hub).
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(String(error)));
      const apps = page.locator('[data-testid="apps-counter"]');
      await openInside(page, tasksScreen);
      await expect(testid(page, 'app-blocked-missing')).toBeVisible();
      await expect.soft(apps, 'Apps slid out').toBeHidden();
      await openInside(page, '/apps');
      await expect(testid(page, 'apps-counter')).toBeVisible();
      await openInside(page, tasksScreen);
      await expect(testid(page, 'app-blocked-missing')).toBeVisible();
      await expect.soft(apps, 'Apps slid out again').toBeHidden();
      // The page it left, as Ionic brings back any page: not a second copy on every visit.
      await expect(page.locator('[data-testid="app-blocked-missing"]'), 'one page of the gate').toHaveCount(1);
      await page.goto(`${A}${tasksScreen}`);
      await expect(testid(page, 'app-blocked-missing')).toBeVisible();
      await snap(page, 'blocked-screen', width);
      expect(errors, 'no error of the page on the screen of an app turned off').toEqual([]);

      // BASE-F24 — «Add apps»: Tasks is there, «Off», with its name; «Turn on» brings it back to the menu.
      await page.goto(`${A}/apps#all`);
      await search(page, 'Tasks');
      await expect(appRow(page, 'task').locator('[data-testid="apps-state"]')).toHaveText('Off');
      await testid(page, 'apps-row-task-toggle').click();
      await expect(appRow(page, 'task').locator('[data-testid="apps-state"]')).toHaveText('Installed');
      await expect(testid(page, 'apps-counter')).toHaveText('17 of 20 apps turned on');
      await expect.poll(() => menuApps(page), { message: 'the menu follows without a reload' }).toContain('Tasks');
      await snap(page, 'on-again', width);
      expect(psql("select state || ':' || chosen from base_appactivation where host = 'a' and app = 'task'")).toBe('on:true');
    } finally {
      await context.close();
    }
  });

  test(`PLAN-HUB §9 — a Gratis business with 20 apps chosen cannot turn on the 21st at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/apps#all');
    try {
      // 20 apps chosen and on, Website off: what an existing business of Gratis may have, at its limit.
      const listed = await api<{ apps: { id: string }[] }>(context, A, 'GET', '/apps');
      const ids = listed.data.apps.map((app) => app.id).filter((id) => id !== 'website');
      expect(ids.length, 'the deployment has more than 20 apps besides Website').toBeGreaterThan(20);
      const values = [
        ...ids.map((id, index) => `('a', '${id}', 'on', ${index < 20 ? 'true' : 'false'})`),
        "('a', 'website', 'off', false)",
      ];
      // In place of the rows `baseline` put back (every app on).
      psql(
        "delete from base_appactivation where host = 'a'; " +
          'insert into base_appactivation (id, host, app, state, chosen, changed_at) ' +
          `select gen_random_uuid(), v.host, v.app, v.state, v.chosen, now() from (values ${values.join(', ')}) as v(host, app, state, chosen)`,
      );
      await pushPhoto(GRATIS);
      await page.reload();

      await expect(testid(page, 'apps-counter')).toHaveText('20 of 20 apps turned on');
      await search(page, 'Website');
      await expect(appRow(page, 'website').locator('[data-testid="apps-state"]')).toHaveText('Off');
      await testid(page, 'apps-row-website-toggle').click();

      const notice = testid(page, 'apps-limit');
      await expect(notice).toContainText('You have reached the 20-app limit of your plan. Upgrade your plan or turn one off.');
      const upgrade = notice.locator('[data-testid="apps-limit-upgrade"]');
      await expect(upgrade).toHaveText('Upgrade plan');
      await expect(upgrade).toHaveAttribute('href', new RegExp(`/dashboard/store/plans\\?business=${hubId}$`));
      await expect(appRow(page, 'website').locator('[data-testid="apps-state"]')).toHaveText('Off');
      expect(psql("select state from base_appactivation where host = 'a' and app = 'website'")).toBe('off');
      await snap(page, 'limit', width);
    } finally {
      await context.close();
    }
  });
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F18 — «Activar» in «Añadir apps» an app the business does not use puts it in «Mis apps» and the menu, at ${width}`, async ({ browser }) => {
    await pushPhoto(GRATIS);
    const { context, page } = await signedInSpanish(browser, viewport, '/apps#all');
    try {
      // A business that does not use Automations (as one born from a vertical without it): off, not in the menu.
      const off = await api<{ app: string; state: string }>(context, A, 'POST', '/apps/disable', { app: 'flow' });
      expect(off, 'Automations off before the flow').toMatchObject({ status: 200, data: { app: 'flow', state: 'off' } });
      await page.reload();
      await expect(testid(page, 'apps-counter')).toHaveText('16 de 20 apps activadas');
      await expect(shown(page).locator('[data-testid="apps-row"]').first()).toBeVisible();
      expect(await namesCutShort(page), `every name whole or ending in «…» at ${width}`).toEqual([]);
      expect(await menuApps(page)).not.toContain('Automatizaciones');
      await search(page, 'Automatizaciones');
      await expect(appRow(page, 'flow').locator('[data-testid="apps-state"]')).toHaveText('Desactivada');

      // It needs no other app: «Activar» turns it on at once, without a question.
      await testid(page, 'apps-row-flow-toggle').click();
      await expect(toast(page, 'Automatizaciones está activada.')).toBeVisible();
      await expect(page.locator('.ep-confirm-dialog:visible')).toHaveCount(0);
      await expect(appRow(page, 'flow').locator('[data-testid="apps-state"]')).toHaveText('Instalada');
      await expect(testid(page, 'apps-counter')).toHaveText('17 de 20 apps activadas');
      expect(stored('flow')).toBe('on:true');
      await expect.poll(() => menuApps(page), { message: 'the menu follows without a reload' }).toContain('Automatizaciones');

      // «Mis apps» lists it, with «Abrir».
      await page.goto(`${A}/apps`);
      await search(page, 'Automatizaciones');
      await expect(appRow(page, 'flow').locator('[data-testid="apps-state"]')).toHaveText('Activa');
      await snap(page, 'mine', width);
      await page.screenshot({ path: shot(`FIX-HUB-BASE-APP-ACTIVATION-BASE-F18-${width}`) });
    } finally {
      await context.close();
    }
  });

  test(`BASE-F19 BASE-F23 BASE-F24 — «Desactivar» Reservas takes Mesas with it and «Activar» brings both back, naming it, at ${width}`, async ({ browser }) => {
    await pushPhoto(GRATIS);
    const { context, page } = await signedInSpanish(browser, viewport, '/apps');
    try {
      await expect(testid(page, 'apps-counter')).toHaveText('17 de 20 apps activadas');
      expect(await menuApps(page)).toEqual(expect.arrayContaining(['Reservas', 'Mesas']));
      await search(page, 'Reservas');

      // BASE-F23 — the question names the app and what goes off with it: Tables, which only Reservations needed.
      await testid(page, 'apps-row-reservation-toggle').click();
      const askOff = page.locator('.ep-confirm-dialog').last();
      await expect(askOff).toContainText('¿Desactivar Reservas?');
      await expect(askOff).toContainText('Mesas se desactiva con ella: solo la necesitaba Reservas.');
      await expect(askOff).toContainText('No se borra nada: al volver a activarla, tiene sus datos.');
      await expect(askOff.getByRole('button', { name: 'Desactivar' })).toBeInViewport({ ratio: 1 });
      await untilStill(page);
      await page.screenshot({ path: shot(`FIX-HUB-BASE-APP-ACTIVATION-BASE-F23-${width}`) });
      await askOff.getByRole('button', { name: 'Desactivar' }).click();
      await expect(toast(page, 'Reservas está desactivada. También se ha desactivado: Mesas.')).toBeVisible();
      await expect(appRow(page, 'reservation')).toHaveCount(0);
      await expect(testid(page, 'apps-counter')).toHaveText('16 de 20 apps activadas');
      expect([stored('reservation'), stored('table')]).toEqual(['off:false', 'off:false']);
      await expect
        .poll(async () => (await menuApps(page)).filter((name) => name === 'Reservas' || name === 'Mesas'), {
          message: 'both leave the menu without a reload',
        })
        .toEqual([]);

      // BASE-F19 and BASE-F24 — «Activar» asks first, naming what turns on with it; the notice names it again.
      await page.goto(`${A}/apps#all`);
      await search(page, 'Reservas');
      await expect(appRow(page, 'reservation').locator('[data-testid="apps-state"]')).toHaveText('Desactivada');
      await testid(page, 'apps-row-reservation-toggle').click();
      const askOn = page.locator('.ep-confirm-dialog').last();
      await expect(askOn).toContainText('¿Activar Reservas?');
      await expect(askOn).toContainText('Reservas necesita Mesas: se activa con ella.');
      await expect(askOn.getByRole('button', { name: 'Activar' })).toBeInViewport({ ratio: 1 });
      await untilStill(page);
      await page.screenshot({ path: shot(`FIX-HUB-BASE-APP-ACTIVATION-BASE-F19-${width}`) });
      await askOn.getByRole('button', { name: 'Activar' }).click();
      await expect(toast(page, 'Reservas está activada. También se ha activado: Mesas.')).toBeVisible();
      await expect(appRow(page, 'reservation').locator('[data-testid="apps-state"]')).toHaveText('Instalada');
      await expect(testid(page, 'apps-counter')).toHaveText('17 de 20 apps activadas');
      // Reservations chosen; Tables came along with it, so it does not count.
      expect([stored('reservation'), stored('table')]).toEqual(['on:true', 'on:false']);
      await expect
        .poll(() => menuApps(page), { message: 'both are back in the menu without a reload' })
        .toEqual(expect.arrayContaining(['Reservas', 'Mesas']));
      await snap(page, 'reservations-on-again', width);
      await page.screenshot({ path: shot(`FIX-HUB-BASE-APP-ACTIVATION-BASE-F24-${width}`) });
    } finally {
      await context.close();
    }
  });

  test(`BASE-F25 — «Desactivar» Mesas while Reservas needs it changes nothing and says what to turn off first, until closed, at ${width}`, async ({ browser }) => {
    await pushPhoto(GRATIS);
    const { context, page } = await signedInSpanish(browser, viewport, '/apps');
    try {
      await search(page, 'Mesas');
      const before = stored('table'); // on, brought along by Reservas (`baseline`)
      expect(before).toBe('on:false');
      await testid(page, 'apps-row-table-toggle').click();

      // No question: it cannot go off. The notice says why and what to do, and stays past a toast's time.
      const refused = testid(page, 'apps-refused');
      await expect(refused).toContainText('No se ha cambiado nada');
      await expect(refused).toContainText('Desactiva antes Reservas.');
      await expect(page.locator('.ep-confirm-dialog:visible')).toHaveCount(0);
      await page.waitForTimeout(5_000); // longer than the 4.5 s of an error toast (hub#2594)
      await expect(refused).toBeVisible();
      await expect(appRow(page, 'table').locator('[data-testid="apps-state"]')).toHaveText('Activa');
      expect(stored('table'), 'nothing written').toBe(before);
      await snap(page, 'refused', width);
      await page.screenshot({ path: shot(`FIX-HUB-BASE-APP-ACTIVATION-BASE-F25-${width}`) });
      await page.screenshot({ path: shot(`FIX-HUB-BASE-APP-ACTIVATION-WORKBOOK-AND-FLOWS-${width}`) });

      // The server says the same if asked anyway: 409, naming the app that needs it.
      const direct = await api<{ error: { code: string; message: string; required_by: string[] } }>(
        context,
        A,
        'POST',
        '/apps/disable',
        { app: 'table' },
      );
      expect(direct.status).toBe(409);
      expect(direct.data.error).toMatchObject({ code: 'base.app_required', message: 'Desactiva antes Reservas.', required_by: ['reservation'] });
      expect(await menuApps(page)).toContain('Mesas');

      // Closed, it goes; nothing else changed.
      await refused.locator('button.close').click();
      await expect(refused).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F25 — «Desactivar» VeriFactu with a record still to send to the AEAT is refused with its reason, at ${width}`, async ({ browser }) => {
    await pushPhoto(GRATIS);
    const { context, page } = await signedInSpanish(browser, viewport, '/apps');
    try {
      // A ticket issued through Invoicing: VeriFactu seals its record, «Pending» until the AEAT answers (never here).
      if (issuedIds.size === 0) {
        await ensureIssuer(context);
        const issued = await api<{ id: string; verifactu_status: string | null }>(context, A, 'POST', '/invoice/invoices', {
          series_code: 'TICKET',
          lines: [{ description: 'e2e BASE-F25 veto', quantity: '1', unit_price: 1000, tax_rate: '21' }],
        });
        expect(issued.status, 'Invoicing issues the ticket').toBe(201);
        expect(issued.data.verifactu_status, 'its record is sealed, still to send').toBe('sealed');
        issuedIds.add(issued.data.id);
      }

      await search(page, 'VeriFactu');
      const before = [stored('verifactu'), stored('invoice')]; // VeriFactu chosen, Invoicing along with it (`baseline`)
      expect(before).toEqual(['on:true', 'on:false']);
      await testid(page, 'apps-row-verifactu-toggle').click();
      const askOff = page.locator('.ep-confirm-dialog').last();
      await expect(askOff).toContainText('¿Desactivar VeriFactu?');
      await askOff.getByRole('button', { name: 'Desactivar' }).click();

      // VeriFactu's own reason, in Spanish, in the notice that stays; nothing changed.
      const refused = testid(page, 'apps-refused');
      await expect(refused).toContainText('No se ha cambiado nada');
      await expect(refused).toContainText(
        /VeriFactu aún tiene (1 registro|\d+ registros) por enviar a la AEAT\. Espera a que se envíe?n? o arréglalos? antes de desactivarla\./,
      );
      await expect(appRow(page, 'verifactu').locator('[data-testid="apps-state"]')).toHaveText('Activa');
      expect([stored('verifactu'), stored('invoice')], 'nothing written').toEqual(before);
      expect(await menuApps(page)).toEqual(expect.arrayContaining(['VeriFactu', 'Facturación']));
      await snap(page, 'vetoed', width);
      await page.screenshot({ path: shot(`FIX-HUB-BASE-APP-ACTIVATION-BASE-F25-veto-${width}`) });
    } finally {
      await context.close();
    }
  });
}

// ── S3: an app whose tables the business's own database lacks is set up first (PLAN-DB §7; BASE-F21, F22) ───────────
// `a` has its own database with every app's tables (`seed_local_hubs`); control's copy of what it has
// (`base_hub.schema_apps`) is told it lacks Printing, so turning Printing on goes through the whole path of a business
// whose database does not have it: the Hub answers 202 «creating», the run's worker (`run_worker --databases-only`) makes
// its tables (`ensure_schema`, a no-op on tables already there: the DDL itself is pytest's, on real databases) and turns
// it on, and the screen and the topbar's «My apps» follow without reloading. «Turning on…» and «Could not turn on» are
// written on the row (the worker set off, or a failure as it leaves it) so each is seen and captured whatever the
// worker's tick; «Retry» goes through the API and the worker again. Captures `APP-BASE-ACTIVATION-S3-<step>-<width>`.

/** The copy the run keeps of what control knows `a`'s database has. */
const SCHEMA = 'e2e_base_app_activation_schema_apps';
const PRINTING = 'printing';

/** Control believes `a`'s database lacks Printing, and Printing is off. */
function printingNotMadeYet(): void {
  psql(
    [
      `drop table if exists ${SCHEMA}`,
      `create table ${SCHEMA} as select id, schema_apps from base_hub where slug = 'a'`,
      `update base_hub set schema_apps = schema_apps - '${PRINTING}' where slug = 'a'`,
    ].join('; '),
  );
  psql(`update base_appactivation set state = 'off', chosen = false where host = 'a' and app = '${PRINTING}'`);
}

function schemaBack(): void {
  psql(
    [
      `update base_hub h set schema_apps = s.schema_apps from ${SCHEMA} s where s.id = h.id`,
      `drop table if exists ${SCHEMA}`,
    ].join('; '),
  );
}

/** The worker is told `a` has work due now, as `base.app.enable` tells it after its COMMIT. */
function ring(): void {
  psql(
    `insert into control_hubdue (hub_id, due_at, lease_owner) values ('${hubId}', now(), '') ` +
      'on conflict (hub_id) do update set due_at = least(control_hubdue.due_at, excluded.due_at)',
  );
}

/** How long the run's worker may take to set an app up: one tick (5 s), the clone-free migration and its settle. */
const SET_UP_MS = 30_000;

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F21 BASE-F22 — an app the business's database lacks is set up, then on, live, at ${width}`, async ({ browser }) => {
    test.setTimeout(180_000);
    printingNotMadeYet();
    const { context, page } = await signedIn(browser, viewport, '/apps#all');
    try {
      await search(page, 'Printing');
      const state = appRow(page, PRINTING).locator('[data-testid="apps-state"]');
      await expect(state).toHaveText('Off');

      // «Turn on»: 202 «creating», and the toast says it is being set up.
      const answered = page.waitForResponse((response) => response.url().endsWith('/api/apps/enable'));
      await testid(page, `apps-row-${PRINTING}-toggle`).click();
      const response = await answered;
      expect([response.status(), (await response.json()).state]).toEqual([202, 'creating']);
      await expect(toast(page, 'Turning on Printing… It will be ready in a moment.')).toBeVisible();

      // The worker sets it up and turns it on: the row and the topbar's «My apps» follow without a reload.
      await expect(state).toHaveText('Installed', { timeout: SET_UP_MS });
      expect(stored(PRINTING)).toBe('on:true');
      expect(psql(`select schema_apps ? '${PRINTING}' from base_hub where slug = 'a'`)).toBe('t');
      // The menu is the session's: AppsFollower reads it again when the live list changes, a moment after.
      await expect.poll(() => menuApps(page), { timeout: SET_UP_MS }).toContain('Printing');
      await snap(page, 'S3-on', width);

      // «Turning on…», as a row the worker set off leaves it: no «Open», and «Turn off» if the business changes its mind.
      psql(
        `update base_appactivation set state = 'creating', next_attempt_at = now() + interval '10 minutes' ` +
          `where host = 'a' and app = '${PRINTING}'`,
      );
      await page.reload();
      await search(page, 'Printing');
      await expect(state).toHaveText('Turning on…');
      await expect(testid(page, `apps-row-${PRINTING}-toggle`)).toContainText('Turn off');
      await expect(testid(page, `apps-row-${PRINTING}-open`)).toHaveCount(0);
      await snap(page, 'S3-creating', width);

      // Its time comes: the worker turns it on and the screen says so, live.
      psql(`update base_appactivation set next_attempt_at = null where host = 'a' and app = '${PRINTING}'`);
      ring();
      await expect(state).toHaveText('Installed', { timeout: SET_UP_MS });

      // «Could not turn on», as a failure leaves the row: «Retry» sets it up again through the worker.
      psql(
        `update base_appactivation set state = 'failed', attempts = 1, last_error = 'schema_failed: e2e', ` +
          `next_attempt_at = now() + interval '1 hour' where host = 'a' and app = '${PRINTING}'`,
      );
      await page.reload();
      await search(page, 'Printing');
      await expect(state).toHaveText('Could not turn on');
      await snap(page, 'S3-failed', width);
      const retried = page.waitForResponse((answer) => answer.url().endsWith('/api/apps/retry'));
      await testid(page, `apps-row-${PRINTING}-retry`).click();
      expect((await retried).status()).toBe(202);
      await expect(toast(page, 'Turning on Printing… It will be ready in a moment.')).toBeVisible();
      await expect(state).toHaveText('Installed', { timeout: SET_UP_MS });
      expect(psql(`select attempts || ':' || last_error from base_appactivation where host = 'a' and app = '${PRINTING}'`)).toBe(
        '0:',
      );
    } finally {
      await context.close();
      schemaBack();
    }
  });
}
