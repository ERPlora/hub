// flow: WHATSAPP_INBOX-F05 WHATSAPP_INBOX-F09
// The WhatsApp inbox with no conversation at all, in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): on
// a phone as on a desk, and with the «reconnect» notice above the list, the list under the search says
// «No conversations.» where the owner can read it, and a search that matches nothing says «No results». Read by hit-testing the centre
// of the empty state: a state that is rendered but clipped by the list's frame (or pushed under the tab
// bar) is not where the point lands. Each size captured (FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12-empty-*).
//
// The hub can invoice during the run (hub#478): Invoicing's red strip «You cannot issue invoices yet» sits over
// every screen, outside the scroller, while the hub has no issuer (base's WORKBOOK, «La franja…»; hub#374), and
// whether it had one depended on the specs run before on the same database. It is not the inbox's notice: at
// 375×667 it takes 138 px, and with the reconnect notice (136) and the search bar (142) the list keeps 97 px in
// view for a 207 px empty state, one scroll away like any list under two notices on that phone. So the run sets
// the issuer up as the owner would (`ensureIssuer`), sees the strip go, and removes the issuer after if it was its.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { ensureIssuer, issuerNow } from './invoice-helpers';
import { noHorizontalScroll, settled } from './service-helpers';
import { cleanUp, metaGraph, pushChannel, restorePhoto, seedErplora } from './whatsapp-helpers';

/** Whether this run set the hub's issuer up (`ensureIssuer` names it `e2e …`), so `afterAll` removes it. */
let ownIssuer = false;

const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

test.beforeAll(async () => {
  // erplora.com's accounts (and `a` with this Hub's id), so the owner signs in on a fresh database too.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
  cleanUp();
});

test.afterAll(() => {
  try {
    cleanUp();
    restorePhoto();
  } finally {
    if (ownIssuer) psql("delete from invoice_issuer where legal_name like 'e2e %'");
  }
});

const empty = (page: Page): Locator => shown(page).locator('[data-testid=whatsapp-inbox-empty]');

/** The element the point at the centre of `locator` lands on is `locator` or inside it. */
async function inSight(locator: Locator): Promise<boolean> {
  return locator.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return hit !== null && (hit === element || element.contains(hit));
  });
}

test('with no conversation the inbox says so in every size, and a search with no match says «No results»', async ({ page }) => {
  // The notice that took the room on a phone (the old nested stack let the list grow by its height).
  pushChannel({ status: 'reconnect_needed' });
  await login(page, A, '/whatsapp_inbox/inbox');
  ownIssuer = !(await issuerNow(page.context())).configured;
  await ensureIssuer(page.context());
  // The server's word, not the strip's absence: the strip waits for its live query, so «none yet» proves nothing.
  const setup = await api<{ blocking_pending: number }>(page.context(), A, 'GET', '/home/setup');
  expect(setup.status).toBe(200);
  expect(setup.data.blocking_pending, 'the hub can invoice: no strip over the inbox').toBe(0);
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-reconnect]')).toBeVisible();
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await settled(page);
    await noHorizontalScroll(page, size.label);
    await expect(empty(page)).toContainText('No conversations.');
    await expect.poll(() => inSight(empty(page)), { message: `empty state in sight at ${size.label}` }).toBe(true);
    await page.screenshot({ path: shot(`FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12-empty-${size.label}`) });
  }

  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill('zz-no-such-contact');
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(empty(page)).toContainText('No results');
    await expect.poll(() => inSight(empty(page)), { message: `no-results state in sight at ${size.label}` }).toBe(true);
  }
});
