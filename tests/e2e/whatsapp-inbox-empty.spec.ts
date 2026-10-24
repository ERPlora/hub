// flow: WHATSAPP_INBOX-F05 WHATSAPP_INBOX-F09
// The WhatsApp inbox with no conversation at all, in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): on
// a phone as on a desk, and with the «reconnect» notice above the list, the list under the search says
// «No conversations.» where the owner can read it, and a search that matches nothing says «No results». Read by hit-testing the centre
// of the empty state: a state that is rendered but clipped by the list's frame (or pushed under the tab
// bar) is not where the point lands. Each size captured (FIX-HUB-WHATSAPP-INBOX-CONNECT-DOORS-10-12-empty-*).
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import { noHorizontalScroll, settled } from './service-helpers';
import { cleanUp, metaGraph, pushChannel, restorePhoto, seedErplora } from './whatsapp-helpers';

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
  cleanUp();
  restorePhoto();
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
