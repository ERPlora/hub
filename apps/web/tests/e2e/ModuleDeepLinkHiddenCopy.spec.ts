// hub#1797 — «Charge» from the agenda with the till already open left TWO tills alive, and the
// hidden one stole the booking.
//
// Measured in a real browser (rv-2040): till → Home → agenda → «Charge». Ionic does NOT bring the
// hidden till page back; it reuses the VISIBLE page (the agenda's) and remounts it as a new till.
// The first till stays mounted in its hidden page, still listening to `popstate`, so it serves
// `?appointment_id=` first, erases it from the address with `replaceState`, and the till on screen
// boots into an empty check («Cobrar 0,00 €»). A component test that faked the Ionic lifecycle by
// hand passed while this happened; this spec runs the real shell, the real Ionic outlet and the
// real runtime, with two tiny modules installed through the dev install route.
//
// The fixtures (`fixtures/modules/*`) follow the module deep-link contract to the letter: the
// agenda pushes the till's address and fires `popstate` (as `appointments` does), the till serves
// the link at boot and on every `popstate` and consumes it (as `sales` does).
import { cpSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const FIXTURES = join(import.meta.dirname, 'fixtures', 'modules');
const MODULE_IDS = ['e2e_till', 'e2e_agenda'] as const;

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
  for (const id of MODULE_IDS) {
    cpSync(join(FIXTURES, id), join(MODULES_DIR, id), { recursive: true });
    await moduleCall('/api/modules/install', { dir: join(MODULES_DIR, id) });
  }
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  for (const id of MODULE_IDS) {
    await moduleCall(`/api/modules/${id}/uninstall`);
    rmSync(join(MODULES_DIR, id), { recursive: true, force: true });
  }
});

/** The runtime serves module assets in production; in this bench Vite does not, so the spec does. */
async function serveFixtureAssets(page: Page): Promise<void> {
  await page.route(/\/modules\/e2e_(till|agenda)\//, async (route) => {
    const url = new URL(route.request().url());
    const [, id, ...rest] = url.pathname.replace(/^\/modules\//, '/').split('/');
    const file = rest[0] === 'v' ? rest.slice(2) : rest; // drop `/v/<version>` (hub#935)
    const path = join(FIXTURES, id, ...file);
    // Optional assets the fixtures do not ship (icons.json, locales) answer what the runtime does.
    if (!existsSync(path)) return route.fulfill({ status: 404, body: '' });
    await route.fulfill({ path });
  });
}

async function openShell(page: Page): Promise<void> {
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user] as const,
  );
  await serveFixtureAssets(page);
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/dashboard$/);
  // The shell mounts once its router is ready (`main.ts`); only then can the spec drive it.
  await page.waitForFunction(() => !!(document.querySelector('#app') as unknown as { __vue_app__?: unknown }).__vue_app__);
}

/** Ionic finished the page transition: exactly one page of the outlet is on screen. A person does
 *  not tap mid-animation, and leaving a page before it settled skips `ionViewDidLeave` entirely. */
async function settled(page: Page): Promise<void> {
  await expect(page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)')).toHaveCount(1);
}

/** In-app navigation the way the launcher and «My apps» do it: through the shell's router. */
async function go(page: Page, path: string): Promise<void> {
  await page.evaluate(async (to) => {
    const app = (document.querySelector('#app') as unknown as {
      __vue_app__: { config: { globalProperties: { $router: { push: (p: string) => Promise<unknown> } } } };
    }).__vue_app__;
    await app.config.globalProperties.$router.push(to);
  }, path);
  await settled(page);
}

const visible = (page: Page, tag: string) =>
  page.locator(tag).filter({ visible: true });

/** The till on screen, open and booted — the state a cashier leaves it in when walking away. */
async function openTill(page: Page): Promise<void> {
  await go(page, '/m/e2e_till/pos');
  await expect(visible(page, 'erp-e2e-till')).toHaveAttribute('data-booted', '1');
  await expect(visible(page, 'erp-e2e-till')).toHaveText('ticket:none');
}

/** «Charge» on the agenda that is on screen, once the page transition has settled on it. */
async function chargeFromAgenda(page: Page): Promise<void> {
  await expect(visible(page, 'erp-e2e-agenda')).toHaveCount(1);
  await visible(page, 'erp-e2e-agenda').getByTestId('e2e-agenda-charge').click();
}

/** Every till still CONNECTED to the document — hidden or not, each one hears `popstate`. */
const connectedTills = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll('erp-e2e-till')].map((el) => ({
      instance: (el as HTMLElement).dataset.instance,
      served: (el as HTMLElement).dataset.served,
      visible: (el as HTMLElement).offsetWidth > 0,
    })),
  );

/** Module screens still alive inside pages Ionic hid — every one of them hears `popstate`. */
const liveInHiddenPages = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll('ion-router-outlet > .ion-page.ion-page-hidden')].flatMap((pg) =>
      [...pg.querySelectorAll('erp-e2e-till, erp-e2e-agenda')].map((el) => el.tagName.toLowerCase()),
    ),
  );

test.describe('a deep link reaches the screen on show, not a hidden copy (hub#1797)', () => {
  test('hub1797_till_home_agenda_charge_opens_the_booking_on_the_visible_till', async ({ page }) => {
    await openShell(page);
    await openTill(page);
    await go(page, '/dashboard');
    await expect(page).toHaveURL(/\/dashboard$/);
    await go(page, '/m/e2e_agenda/list');
    await chargeFromAgenda(page);

    // 🔴 The defect: the till on screen opened empty because a hidden till served the booking.
    await expect(visible(page, 'erp-e2e-till')).toHaveText('ticket:T1');
    const tills = await connectedTills(page);
    expect(tills, 'a hidden till is still connected and listening').toHaveLength(1);
    expect(tills[0]).toMatchObject({ served: 'T1', visible: true });
    expect(await liveInHiddenPages(page)).toEqual([]);
  });

  test('till → agenda → charge opens the booking on one till', async ({ page }) => {
    await openShell(page);
    await openTill(page);
    // A slow shop wifi: the page the till leaves starts mounting the agenda (its route watcher runs
    // before `ionViewDidLeave`) and that mount is still waiting on the runtime when Ionic hides it.
    await page.route('**/api/**', async (route) => {
      await new Promise((r) => setTimeout(r, 700));
      await route.continue();
    });
    await go(page, '/m/e2e_agenda/list');
    await chargeFromAgenda(page);

    await expect(visible(page, 'erp-e2e-till')).toHaveText('ticket:T1');
    const tills = await connectedTills(page);
    expect(tills).toHaveLength(1);
    expect(tills[0]).toMatchObject({ served: 'T1', visible: true });
    // The page the till left was remounted as a SECOND agenda before Ionic hid it (its route
    // watcher runs before `ionViewDidLeave`): a hidden screen nobody sees, still listening.
    expect(await liveInHiddenPages(page), 'a hidden page still runs a module screen').toEqual([]);
  });

  test('going back to the till shows a working till, and only one', async ({ page }) => {
    // The other half of the fix: a page that let go of its module when it left mounts it again
    // when Ionic hands it back. Settings is pushed ON TOP of the till, so `history.back` returns
    // to that very page (`ionViewWillEnter`) instead of building a new one — it must not be blank.
    await openShell(page);
    await openTill(page);
    await go(page, '/settings');
    await expect(page).toHaveURL(/\/settings/);
    expect(await liveInHiddenPages(page), 'the till kept running behind Settings').toEqual([]);

    await page.goBack();
    await settled(page);

    await expect(page).toHaveURL(/\/m\/e2e_till\/pos$/);
    await expect(visible(page, 'erp-e2e-till')).toHaveText('ticket:none');
    expect(await connectedTills(page)).toHaveLength(1);
  });
});
