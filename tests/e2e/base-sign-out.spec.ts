// flow: BASE-F61 (base/WORKBOOK.md, «Cerrar sesión») · ACCOUNTS-F09 of the SaaS (accounts/WORKBOOK.md)
// FIX-HUB-BASE-LOGOUT-LANDS-ON-SAAS-404: «Sign out» of a business on a device without the PIN pad ends the Hub's
// session and goes on to erplora.com, which asks before closing its own (a redirect is a GET, and a GET never signs
// anybody out), never to the 404 of allauth's old `/accounts/logout/`. «Stay signed in» keeps erplora.com's session (the
// launcher with the account's business); «Sign out» ends it too, and erplora.com and the business ask to sign in again.
// The real Hub and the real SaaS of this run's stack; a fresh account signed up on the SaaS's screens and its business
// created through the SaaS's API, as the panel creates it (base-access.spec.ts): signing out of erplora.com ends that
// account's session there, so never the demo accounts whose erplora.com session the other specs reuse (`login`).
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { api, type Credentials, login, MAIL_DIR, psql, SAAS, shot, shown, untilStill } from './helpers';
import { readMailCode } from './mail';
import { STACK } from './stack';

const KEY = 'FIX-HUB-BASE-LOGOUT-LANDS-ON-SAAS-404';
const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const SAAS_STEP = 30_000;
/** erplora.com's «Sign out of erplora.com?» (saas `accounts/frontend/pages/SignOutPage.vue`). */
const SIGN_OUT_PAGE = `${SAAS}/logout`;
const LAUNCHER = `${SAAS}/launch`;

test.describe.configure({ mode: 'serial' });

let context: BrowserContext;
let page: Page;
let credentials: Credentials;
let origin: string;

test.beforeAll(async ({ browser }) => {
  credentials = { email: `e2e-sign-out-${Date.now()}@example.com`, password: PASSWORD };
  context = await browser.newContext({ locale: 'en-US', viewport: { width: 1440, height: 900 } });
  page = await context.newPage();
  await page.goto(`${LAUNCHER}?tab=signup`);
  const form = page.getByTestId('login-form');
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  const since = Date.now() - 50;
  await form.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/verify-email$/);
  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since, timeout: SAAS_STEP });
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).toHaveURL(/\/launch$/);

  const host = new URL(SAAS).hostname;
  const csrf = (await context.cookies(SAAS)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const created = await context.request.post(`${SAAS}/api/hubs/businesses`, {
    headers: { 'X-CSRFToken': csrf },
    data: { name: `Sign out ${Date.now().toString(36)}`, country: 'ES' },
  });
  expect(created.status(), await created.text()).toBe(201);
  const business = (await created.json()) as { id: string; slug: string };
  await expect
    .poll(() => psql(`SELECT status FROM base_hub WHERE id = '${business.id}'`), { timeout: SAAS_STEP, message: 'registered here' })
    .toBe('ready');
  origin = STACK.hub(business.slug);
});

test.afterAll(async () => {
  await context?.close();
});

/** «Sign out» of the business's user menu (pinned at 1440): the status of the page the browser lands on. */
async function signOutOfTheBusiness(): Promise<number> {
  await page.setViewportSize({ width: 1440, height: 900 });
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name').click();
  await presented;
  const landed = page.waitForResponse((response) => response.url() === SIGN_OUT_PAGE && response.request().resourceType() === 'document');
  await page.locator('ion-popover [data-testid="user-menu-logout"]').click();
  return (await landed).status();
}

test('BASE-F61: «Sign out» on a personal device lands on erplora.com’s question, never a 404; «Stay signed in» keeps its session', async ({ browser }) => {
  await login(page, origin, '/', credentials);
  expect(await signOutOfTheBusiness()).toBe(200);
  await expect(page).toHaveURL(SIGN_OUT_PAGE);
  const question = shown(page);
  await expect(question.locator('h2.auth-title')).toHaveText('Sign out of erplora.com?');
  await expect(question.getByTestId('sign-out-lead')).toHaveText(
    `You are still signed in to erplora.com in this browser as ${credentials.email}.`,
  );
  await expect(question.getByTestId('sign-out-confirm')).toHaveText('Sign out');
  await expect(question.getByTestId('sign-out-stay')).toHaveText('Stay signed in');
  // The business's session is over already: its API knows nobody in this browser.
  expect((await api<{ user: unknown }>(context, origin, 'GET', '/me')).data.user).toBeNull();
  // Each capture in a browser of its own size with this session, the question loaded there (opening it closes nothing):
  // a capture right after `setViewportSize` sometimes painted the header a second time at the foot (390 and 834, either
  // with `fullPage` or not), though the page had one header at the top; a page loaded at its size never did.
  const signedIn = await context.storageState();
  for (const size of SIZES) {
    const sized = await browser.newContext({ locale: 'en-US', viewport: { width: size.width, height: size.height }, storageState: signedIn });
    const atSize = await sized.newPage();
    await atSize.goto(SIGN_OUT_PAGE);
    await expect(shown(atSize).getByTestId('sign-out-confirm')).toBeVisible();
    await untilStill(atSize);
    await atSize.screenshot({ path: shot(`${KEY}-${size.name}`) });
    await sized.close();
  }

  await shown(page).getByTestId('sign-out-stay').click();
  await expect(page).toHaveURL(LAUNCHER);
  // Still signed in to erplora.com: the launcher names the account under the card, with its business.
  await expect(shown(page).getByTestId('shell-account')).toContainText(credentials.email);
});

test('BASE-F61: «Sign out» there ends erplora.com’s session too: erplora.com and the business ask to sign in again', async () => {
  // Back into the business without typing anything: erplora.com kept its session.
  await login(page, origin, '/', credentials, { fresh: true });
  expect(await signOutOfTheBusiness()).toBe(200);
  await shown(page).getByTestId('sign-out-confirm').click();
  await expect(page).toHaveURL(LAUNCHER);
  await expect(page.getByTestId('login-form')).toBeVisible();
  await page.goto(`${SAAS}/dashboard/businesses`);
  await expect(page).toHaveURL(/\/launch\?next=/);
  await expect(page.getByTestId('login-form')).toBeVisible();
  // The business sends whoever comes to erplora.com's sign-in, which asks for the account again.
  await page.goto(`${origin}/`);
  await page.waitForURL((url) => url.origin === SAAS);
  await expect(page.getByTestId('login-form')).toBeVisible();
});
