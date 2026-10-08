// Regression test for ERPlora/hub#2539 and ERPlora/hub#2538 — after «Switch user» on a shared till,
// the screen the previous person left open kept showing what SHE could see, and the assistant panel
// kept what she had typed and attached without sending.
//
// Both are the same defect: the hand-over (`switchUser`, hub#456) swaps the session without
// navigating — on purpose, so the sale is not lost — and until here it only forgot state that lives
// in libraries (tokens, profile, launcher, the assistant's thread). What was MOUNTED stayed mounted:
// the page in the outlet (and the pages Ionic keeps hidden behind it for «back»), with whatever it
// had read for her, and the assistant panel with its draft, attachments and quota notice.
//
// What a hand-over does now, as Square and Toast do it:
//   - the screen in front of the till is mounted again for the person who arrived, so it re-reads
//     everything with HER permissions — and the hidden pages of the previous person are gone;
//   - if she cannot open that screen at all (the app or its tab is not in her launcher), the till
//     lands on Home instead;
//   - the assistant panel closes and starts from scratch: no draft, no attachments, no notice, no
//     «review the setup» mode.
//
// It runs the real shell, the real Ionic outlet and the real runtime: the person who arrives is a
// real employee the runtime refuses the report to, and two tiny modules are installed through the
// dev install route (as `ModuleDeepLinkHiddenCopy.spec.ts` does).
//
// 🔴 The file name is load-bearing: it sorts AFTER the visual specs. The person it creates cannot be
// deleted —removal deactivates, and `/employees` paints inactive rows too— so no visual contract may
// run after it.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const FIXTURES = join(import.meta.dirname, 'fixtures', 'modules');
/** `e2e_report`: only an administrator may open it. `e2e_till`: everybody may. */
const MODULE_IDS = ['e2e_report', 'e2e_till'] as const;

/** Prefix of the person this spec creates. Also its clean-up tag. */
const PREFIX = 'QA Relevo ';
/** A PIN this bench accepts: six digits, no progression. */
const PIN = '583914';
/** What the report shows to whoever may read it (`fixtures/modules/e2e_report`). */
const SECRET_FIGURE = 'margin-4242';

interface Session {
  token: string;
  user: unknown;
}

interface HubUser {
  id: string;
  name: string;
  is_active?: boolean;
}

let admin: Session;
let employee: HubUser;

async function hubApi<T>(method: 'GET' | 'POST' | 'DELETE', path: string, data?: unknown): Promise<T> {
  const api = await pwRequest.newContext();
  const res = await api.fetch(`${RUNTIME}${path}`, {
    method,
    data: data ?? (method === 'POST' ? {} : undefined),
    headers: { 'X-Hub-Session': admin.token },
  });
  const text = await res.text();
  await api.dispose();
  expect(res.ok(), `${method} ${path}: ${res.status()} ${text}`).toBeTruthy();
  return (text ? (JSON.parse(text) as { data: T }).data : undefined) as T;
}

test.beforeAll(async () => {
  expect(MODULES_DIR, 'playwright.config.ts exports the bench modules folder').not.toBe('');
  admin = await loginByPin();
  // A run that died before its clean-up leaves this PIN taken: deactivate leftovers first.
  const users = await hubApi<HubUser[]>('GET', '/api/hub/users');
  for (const u of users.filter((x) => x.name.startsWith(PREFIX) && x.is_active !== false)) {
    await hubApi('DELETE', `/api/hub/users/${u.id}`);
  }
  employee = await hubApi<HubUser>('POST', '/api/hub/users', {
    name: `${PREFIX}${Date.now()}`,
    email: '',
    role: 'employee',
    pin: PIN,
    local: true,
  });
  for (const id of MODULE_IDS) {
    cpSync(join(FIXTURES, id), join(MODULES_DIR, id), { recursive: true });
    await hubApi('POST', '/api/modules/install', { dir: join(MODULES_DIR, id) });
  }
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  for (const id of MODULE_IDS) {
    await hubApi('POST', `/api/modules/${id}/uninstall`);
    rmSync(join(MODULES_DIR, id), { recursive: true, force: true });
  }
  if (employee) await hubApi('DELETE', `/api/hub/users/${employee.id}`);
});

/**
 * The till as a counter till: `shared`, trusted, asking for a PIN — the only device the hand-over
 * is offered on (`offersUserSwitch`). Trust is only ever granted by an online sign-in, which this
 * bench has no erplora.com for; the runtime already accepts the PIN without it
 * (`HUB_DEVICE_TRUST=off`), so only the device's own answer is stated here. Nothing else is faked.
 */
async function asCounterTill(page: Page): Promise<void> {
  await page.route('**/api/device/mode', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    await route.fulfill({ json: { ok: true, data: { mode: 'shared', pin_policy: 'per_shift', trusted: true } } });
  });
}

/** The runtime serves module assets in production; in this bench Vite does not, so the spec does. */
async function serveFixtureAssets(page: Page): Promise<void> {
  await page.route(/\/modules\/e2e_(report|till)\//, async (route) => {
    const url = new URL(route.request().url());
    const [, id, ...rest] = url.pathname.replace(/^\/modules\//, '/').split('/');
    const file = rest[0] === 'v' ? rest.slice(2) : rest; // drop `/v/<version>` (hub#935)
    const path = join(FIXTURES, id, ...file);
    if (!existsSync(path)) return route.fulfill({ status: 404, body: '' });
    await route.fulfill({ path });
  });
}

interface ShellRouter {
  push: (p: string) => Promise<unknown>;
  currentRoute: { value: { fullPath: string } };
}

const currentPath = (page: Page): Promise<string> =>
  page.evaluate(
    () =>
      (document.querySelector('#app') as unknown as {
        __vue_app__: { config: { globalProperties: { $router: ShellRouter } } };
      }).__vue_app__.config.globalProperties.$router.currentRoute.value.fullPath,
  );

/** Ionic finished the page transition: exactly one page of the outlet is on screen. */
async function settled(page: Page): Promise<void> {
  await expect(page.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)')).toHaveCount(1);
}

/** In-app navigation, the way the launcher does it: through the shell's router. */
async function go(page: Page, path: string): Promise<void> {
  await page.evaluate((to) => {
    const app = (document.querySelector('#app') as unknown as {
      __vue_app__: { config: { globalProperties: { $router: ShellRouter } } };
    }).__vue_app__;
    void app.config.globalProperties.$router.push(to);
  }, path);
  await expect.poll(() => currentPath(page)).toBe(path);
  await settled(page);
}

async function openShellAsAdmin(page: Page): Promise<void> {
  await asCounterTill(page);
  await serveFixtureAssets(page);
  // A session of its own: the hand-over revokes the browser's token, and the spec's API calls
  // (`admin`) must outlive it.
  await withSession(page, await loginByPin());
  await page.goto('/dashboard');
  await page.waitForFunction(() => !!(document.querySelector('#app') as unknown as { __vue_app__?: unknown }).__vue_app__);
  await settled(page);
}

/** «Switch user» from the user card, the employee's face, her PIN — as a person does it. */
async function handTillToEmployee(page: Page): Promise<void> {
  await page.locator('#sidebar-user-menu').click();
  await page.locator('[data-testid="switch-user-item"]').click();
  await page.locator('[data-testid="user-switch-person"]', { hasText: employee.name }).click();
  const pinpad = page.locator('[data-testid="user-switch-pinpad"]');
  for (const digit of PIN) await pinpad.getByRole('button', { name: digit, exact: true }).click();
  // The swap is done when the till's user card names her.
  await expect(page.locator('#sidebar-user-menu')).toContainText(employee.name);
}

/** Opens the assistant as a person does: from the topbar (on a phone, from its overflow). */
async function openAssistant(page: Page): Promise<void> {
  const direct = page.locator('[data-testid="topbar-assistant"]');
  if (await direct.isVisible().catch(() => false)) {
    await direct.click();
  } else {
    await page.locator('[data-testid="topbar-more"]').click();
    await page.locator('[data-testid="topbar-more-assistant"]').click();
  }
  await expect(page.locator('[data-testid="assistant-drawer"]')).toHaveAttribute('data-open', 'true');
}

test.describe('Switch user leaves nothing of the previous person on screen (hub#2539, hub#2538)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('a report she may not open is replaced by Home, and nothing of it stays in the page', async ({ page }) => {
    await openShellAsAdmin(page);
    await go(page, '/m/e2e_report/figures');
    await expect(page.locator('erp-e2e-report')).toContainText(SECRET_FIGURE);

    await handTillToEmployee(page);

    await expect.poll(() => currentPath(page), 'she cannot open the report: the till lands on Home').toBe('/dashboard');
    await settled(page);
    // Not visible AND not hidden behind Home for «back»: the previous person's page is gone.
    await expect(page.locator('erp-e2e-report')).toHaveCount(0);
    expect(await page.content()).not.toContain(SECRET_FIGURE);
  });

  test('a screen she may open is mounted again for her, without the previous person’s hidden pages', async ({ page }) => {
    await openShellAsAdmin(page);
    // The admin passed by the report and then opened the till: Ionic keeps the report hidden behind.
    await go(page, '/m/e2e_report/figures');
    await expect(page.locator('erp-e2e-report')).toContainText(SECRET_FIGURE);
    await go(page, '/m/e2e_till/pos');
    const till = page.locator('erp-e2e-till').filter({ visible: true });
    await expect(till).toHaveAttribute('data-booted', '1');
    const before = await till.getAttribute('data-instance');

    await handTillToEmployee(page);

    // The till stays where it was (the sale is not lost: it is server-side, ADR-0144/0146)…
    await expect.poll(() => currentPath(page)).toBe('/m/e2e_till/pos');
    await settled(page);
    // …but the page is a new one, mounted under her session.
    await expect(till).toHaveAttribute('data-booted', '1');
    expect(await till.getAttribute('data-instance'), 'the till was mounted again for her').not.toBe(before);
    await expect(page.locator('erp-e2e-report')).toHaveCount(0);
    expect(await page.content()).not.toContain(SECRET_FIGURE);
  });

  test('the assistant closes and starts empty: no draft, no attachments', async ({ page }) => {
    await openShellAsAdmin(page);
    await openAssistant(page);
    await page.locator('[data-testid="assistant-input"] textarea').fill('note only the manager wrote');
    await page.locator('[data-testid="assistant-attach-input"]').setInputFiles({
      name: 'margins.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from(SECRET_FIGURE),
    });
    await expect(page.locator('.attach-chip')).toHaveCount(1);

    await handTillToEmployee(page);

    await expect(page.locator('[data-testid="assistant-drawer"]')).toHaveAttribute('data-open', 'false');
    await openAssistant(page);
    await expect(page.locator('[data-testid="assistant-input"] textarea')).toHaveValue('');
    await expect(page.locator('.attach-chip')).toHaveCount(0);
  });
});
