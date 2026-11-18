// The stack's SaaS as the specs meet it: its address, its demo accounts and the folder of the mails with their
// codes, where its sign-in posts, and «Upgrade plan» landing inside its plans.
import { expect, type Locator, type Page } from '@playwright/test';

import { mailDirFrom } from './mail';
import { psql } from './psql';
import { REPO_DIR, STACK } from './stack';

/** The SaaS (`erplora.com` in production): the only login page a hub has. */
export const SAAS = STACK.saas;

/** «Upgrade plan» pressed in a browser with no session of erplora.com (BASE-F11): a tab of its own lands inside `a`'s
 *  plans by a pass, never on the sign-in form, and cannot reach back into the hub. */
export async function upgradeLandsInside(page: Page, link: Locator): Promise<void> {
  const context = page.context();
  // Only the SaaS's cookies (host `localhost`): the hub's session, on `a.localhost`, stays.
  await context.clearCookies({ domain: new URL(SAAS).hostname });
  const inside = `${SAAS}/dashboard/store/plans?business=${psql("SELECT id FROM base_hub WHERE slug = 'a'")}`;
  const passes: string[] = [];
  const seen = (request: { url(): string }) => {
    if (request.url().startsWith(`${SAAS}/hub-pass/?pass=`)) passes.push(request.url());
  };
  context.on('request', seen);
  const before = context.pages().length;
  const [tab] = await Promise.all([page.waitForEvent('popup'), link.click()]);
  await tab.waitForURL((url) => url.href.startsWith(inside));
  await expect(tab.getByTestId('store-plans')).toBeVisible();
  await expect(tab.getByTestId('login-form')).toHaveCount(0);
  expect(await tab.evaluate(() => window.opener), 'the new tab cannot reach back into the hub').toBeNull();
  expect(context.pages(), 'one tab, not two: the click did not also follow the link').toHaveLength(before + 1);
  expect(passes, 'through the door with one pass').toHaveLength(1);
  context.off('request', seen);
  await tab.close();
}
/**
 * Whether `page` is on the SaaS (its login): what its console says there is the SaaS's, judged by the SaaS's own
 * suite. Its headless API answers 401 while nobody is signed in (allauth's protocol), and Chrome logs each one.
 */
export const onSaas = (page: Page): boolean => new URL(page.url()).origin === SAAS;
/** A SaaS account: what its sign-in page asks for. */
export interface Credentials {
  email: string;
  password: string;
}
/** The demo customer account in the SaaS (`saas … demo_seed`): owner of hubs `a` and `b`. */
export const OWNER: Credentials = { email: 'owner@example.com', password: 'owner' };
/** The demo employee in the SaaS (`demo_seed`): `hub_employee` of `a` and `b`, views Demo only. */
export const EMPLOYEE: Credentials = { email: 'employee@example.com', password: 'employee' };
/** Where the local SaaS writes its mails (Django's file backend): `saas/.mail` beside the Hub, or `E2E_MAIL_DIR`. */
export const MAIL_DIR = mailDirFrom(process.env, REPO_DIR);
/** Slack between our clock and the mail file's modification time, in ms. */
export const MAIL_CLOCK_SLACK = 50;

/** Where the SaaS's sign-in form posts the account (allauth.headless). */
export const SAAS_SIGN_IN = `${SAAS}/_allauth/browser/v1/auth/login`;
/** Where the SaaS's code form posts the code it mailed (allauth.headless). */
export const SAAS_CODE = `${SAAS}/_allauth/browser/v1/auth/code/confirm`;
/** The SaaS's page that says why it refused a sign-in or a jump to a hub (`?code=not_a_member`, `too_many`…): nothing goes on from there by itself. */
export const SAAS_REFUSED = '/login/error';
