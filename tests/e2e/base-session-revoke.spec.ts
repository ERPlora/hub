// flow: BASE-F13 (base/WORKBOOK.md) · HUBS-F26 and HUBS-F27 of the SaaS (hubs/WORKBOOK.md)
// The owner changes an employee's role, or removes them from the business, in erplora.com's panel. The SaaS ends that
// person's sessions in the Hub (`POST /internal/sessions/revoke`, after its COMMIT) and pushes the photo with the
// business's members. The employee's open tab loses its session at once (every call answers 401) and, when they come
// back to the business: with the new role after a change (a manager's «New item»), the SaaS's «You don't have access
// to this hub» after a removal.
// The real Hub and the real SaaS of this run's stack (the SaaS's `HUB_INTERNAL_URL` points here) and fresh accounts
// signed up on the SaaS's screens; the business is created through the SaaS's API as the panel creates it, so the SaaS
// registers it in this Hub with the same id. The SaaS's changes are made on its panel, as the owner makes them.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { api, type Credentials, listReady, login, MAIL_DIR, psql, SAAS, shot, shown } from './helpers';
import { readMailCode } from './mail';
import { STACK } from './stack';

const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
/** What the SaaS's steps wait (its pushes to this Hub happen after its COMMIT). */
const SAAS_STEP = 30_000;

interface Person {
  context: BrowserContext;
  page: Page;
  credentials: Credentials;
}

interface Business {
  id: string;
  slug: string;
}

/** A fresh account signed up on the SaaS's «Create account», its address proven with the mailed code; signed in. */
async function signUp(browser: Browser, who: string): Promise<Person> {
  const credentials = { email: `e2e-revoke-${who}-${Date.now()}@example.com`, password: PASSWORD };
  const context = await browser.newContext({ locale: 'en-US', viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${SAAS}/launch?tab=signup`);
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
  return { context, page, credentials };
}

/** A POST to the SaaS's API as `context`'s account, with the SaaS's CSRF token. */
async function saasPost(context: BrowserContext, path: string, data: unknown) {
  const host = new URL(SAAS).hostname;
  const csrf = (await context.cookies(SAAS)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value;
  if (!csrf) throw new Error(`POST ${path}: no csrftoken of the SaaS (sign in first)`);
  return context.request.post(`${SAAS}/api${path}`, { headers: { 'X-CSRFToken': csrf }, data });
}

/** `owner`'s new business, once the SaaS registered it in this Hub and heard it is ready. */
async function businessOf(owner: Person): Promise<Business> {
  const created = await saasPost(owner.context, '/hubs/businesses', { name: `Revoke ${Date.now().toString(36)}`, country: 'ES' });
  expect(created.status(), await created.text()).toBe(201);
  const business = (await created.json()) as Business;
  await expect
    .poll(() => psql(`SELECT status FROM base_hub WHERE id = '${business.id}'`), { timeout: SAAS_STEP, message: 'registered here' })
    .toBe('ready');
  await expect
    .poll(
      async () => {
        const detail = await owner.context.request.get(`${SAAS}/api/hubs/businesses/detail?id=${business.id}`);
        return ((await detail.json()) as { status?: string }).status;
      },
      { timeout: SAAS_STEP, message: 'active in the SaaS' },
    )
    .toBe('active');
  return business;
}

/** `person` joins `business` as an employee: the owner invites them and they accept, through the SaaS's API. */
async function joins(owner: Person, person: Person, business: Business): Promise<string> {
  const invited = await saasPost(owner.context, '/hubs/members/invite', {
    hub_id: business.id,
    email: person.credentials.email,
    role: 'hub_employee',
    message: '',
  });
  expect(invited.status(), await invited.text()).toBe(200);
  const { id } = (await invited.json()) as { id: string };
  const accepted = await saasPost(person.context, '/hubs/invitations/accept', { id });
  expect(accepted.status(), await accepted.text()).toBe(200);
  return id;
}

/** The owner's panel: the business's «Team», on screen. */
async function team(owner: Person, business: Business): Promise<Page> {
  const panel = owner.page;
  await panel.goto(`${SAAS}/businesses/${business.id}/members`);
  await expect(panel.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last().getByTestId('members-row').first()).toBeVisible();
  return panel;
}

/** The panel's row action `action` of the member `memberId`. */
function rowAction(panel: Page, memberId: string, action: string) {
  return panel.locator('ion-router-outlet > .ion-page:not(.ion-page-hidden)').last().getByTestId(`members-row-${memberId}-${action}`);
}

/** Until the Hub refuses the tab's session: the SaaS's revocation arrived. */
async function sessionEnded(person: Person, origin: string): Promise<void> {
  await expect
    .poll(async () => (await api(person.context, origin, 'GET', '/demo/items')).status, {
      timeout: SAAS_STEP,
      message: 'the tab still has its session',
    })
    .toBe(401);
}

/** `ready` at each size and a capture `APP-HUBS-3-<key>-<size>`; back at 1440 after. */
async function atEverySize(page: Page, key: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    // A frame's callbacks run before it is painted; the next frame's, once the new size has been.
    await page.evaluate(() => new Promise<void>((painted) => requestAnimationFrame(() => requestAnimationFrame(() => painted()))));
    await page.screenshot({ path: shot(`APP-HUBS-3-${key}-${size.name}`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

// Two accounts per run: the SaaS lets 10 sign-ups an hour from one address (`ACCOUNT_RATE_LIMITS`), and an account
// owns one free business. The role changes first, then the same person is removed: one business, in this order.
test.describe.configure({ mode: 'serial' });

let owner: Person;
let employee: Person;
let business: Business;
let memberId: string;
let origin: string;
let tab: Page;

test.beforeAll(async ({ browser }) => {
  owner = await signUp(browser, 'owner');
  employee = await signUp(browser, 'employee');
  business = await businessOf(owner);
  memberId = await joins(owner, employee, business);
  origin = STACK.hub(business.slug);
  tab = await employee.context.newPage();
});

test.afterAll(async () => {
  await owner?.context.close();
  await employee?.context.close();
});

test("BASE-F13 (HUBS-F26): a new role ends the employee's session in the business; back in, they work with it", async () => {
  await login(tab, origin, '/demo/items', employee.credentials);
  await listReady(tab);
  await atEverySize(tab, 'BASE-F13-employee', async () => {
    await listReady(tab);
    await expect(shown(tab).locator('[data-testid=demo-items-add]')).toHaveCount(0);
  });

  const panel = await team(owner, business);
  await rowAction(panel, memberId, 'change_role').click();
  const modal = panel.getByTestId('role-modal');
  await expect(modal).toBeVisible();
  await panel.getByTestId('role-select').click();
  await panel.locator('ion-popover ion-radio', { hasText: 'Manager' }).click();
  await panel.getByTestId('role-modal-submit').click();
  await expect(modal).toBeHidden();

  // The open tab: its session ended in the Hub, and the photo says the new role.
  await sessionEnded(employee, origin);
  expect(
    psql(
      `SELECT state->'members' @> jsonb_build_array(jsonb_build_object('role', 'hub_manager')) FROM base_hub WHERE id = '${business.id}'`,
    ),
  ).toBe('t');

  // Back in: through the SaaS (still signed in there), with the new role: a manager adds items.
  await login(tab, origin, '/demo/items', employee.credentials);
  await atEverySize(tab, 'BASE-F13-manager', async () => {
    await listReady(tab);
    await expect(shown(tab).locator('[data-testid=demo-items-add]')).toBeVisible();
  });
  expect((await api(employee.context, origin, 'GET', '/demo/items')).status).toBe(200);
});

test('BASE-F13 (HUBS-F27): a person removed from the business loses their session there and cannot come back', async () => {
  await login(tab, origin, '/demo/items', employee.credentials);
  await listReady(tab);

  const panel = await team(owner, business);
  await rowAction(panel, memberId, 'remove').click();
  const dialog = panel.getByTestId('remove-dialog');
  await expect(dialog).toBeVisible();
  await panel.getByTestId('remove-dialog-submit').click();
  await expect(dialog).toBeHidden();

  await sessionEnded(employee, origin);
  expect(
    psql(
      `SELECT count(*) FROM base_membership m JOIN auth_user u ON u.id = m.user_id WHERE m.host = '${business.slug}' AND u.email = '${employee.credentials.email}'`,
    ),
  ).toBe('0');

  // Coming back sends them to the SaaS, which says they have no access to this hub.
  await tab.goto(`${origin}/demo/items`);
  await expect(tab).toHaveURL(new RegExp(`^${SAAS}/login/error\\?code=not_a_member`));
  await atEverySize(tab, 'BASE-F13-removed', async () => {
    await expect(tab.getByRole('heading', { name: "You don't have access to this hub" })).toBeVisible();
    await expect(tab.getByTestId('login-error-badge')).toHaveText('403 · No access');
  });
  expect((await api(employee.context, origin, 'GET', '/demo/items')).status).toBe(401);
});
