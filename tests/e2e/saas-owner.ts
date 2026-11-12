// A fresh owner on the stack's SaaS, as a person signs up on erplora.com: an account made on its «Create account» (its
// address proven with the code it mails, read from the run's mail folder) and its business, created through the SaaS's
// API as the panel does, which the SaaS registers in this Hub and the worker makes. Every spec that needs an owner of
// its own takes them from here (saas-owner.test.ts keeps it so); the Hub's API stays `api`'s (hub-api.test.ts).
import { type Browser, type BrowserContext, expect, type Page } from '@playwright/test';

import { type Credentials, MAIL_CLOCK_SLACK, MAIL_DIR, psql, SAAS } from './helpers';
import { readMailCode } from './mail';

/** The password of every account a spec signs up on the SaaS. */
const SAAS_PASSWORD = 'Masa-madre-y-centeno-26';
/** What each of the SaaS's steps waits: its pushes to this Hub happen after its COMMIT, and the worker makes the
 *  business's database after it. */
const SAAS_STEP = 30_000;

/** An account signed up on the SaaS, with its browser signed in there. */
export interface SaasOwner {
  context: BrowserContext;
  page: Page;
  credentials: Credentials;
}

/** A business the SaaS registered in this Hub (`PUT /internal/hubs/{id}`), with the SaaS's id. */
export interface SaasBusiness {
  id: string;
  slug: string;
}

/** A fresh account (`e2e-<prefix>-<time>@example.com`) signed up on the SaaS's «Create account», its address proven
 *  with the mailed code; signed in there. One free business per account (`FREE_HUBS_PER_ACCOUNT`): a spec signs up one
 *  per business it needs. */
export async function signUpOnSaas(browser: Browser, prefix: string): Promise<SaasOwner> {
  const credentials = { email: `e2e-${prefix}-${Date.now()}@example.com`, password: SAAS_PASSWORD };
  const context = await browser.newContext({ locale: 'en-US', viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${SAAS}/launch?tab=signup`);
  const form = page.getByTestId('login-form');
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  const since = Date.now() - MAIL_CLOCK_SLACK;
  await form.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/verify-email$/);
  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since, timeout: SAAS_STEP });
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).toHaveURL(/\/launch$/);
  return { context, page, credentials };
}

/** A POST to the SaaS's API as `context`'s account, with the SaaS's CSRF token. */
export async function saasPost(context: BrowserContext, path: string, data: unknown) {
  const host = new URL(SAAS).hostname;
  const csrf = (await context.cookies(SAAS)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value;
  if (!csrf) throw new Error(`POST ${path}: no csrftoken of the SaaS (sign in first)`);
  return context.request.post(`${SAAS}/api${path}`, { headers: { 'X-CSRFToken': csrf }, data });
}

/** `owner`'s new business, created on the SaaS as its panel does (`POST /api/hubs/businesses`), once this Hub
 *  registered it and its worker made its database (`ready`). */
export async function businessOnSaas(owner: SaasOwner, business: { name: string; country: string }): Promise<SaasBusiness> {
  const created = await saasPost(owner.context, '/hubs/businesses', business);
  expect(created.status(), await created.text()).toBe(201);
  const made = (await created.json()) as SaasBusiness;
  await expect
    .poll(() => psql(`SELECT status FROM base_hub WHERE id = '${made.id}'`), { timeout: SAAS_STEP, message: 'registered here' })
    .toBe('ready');
  return made;
}
