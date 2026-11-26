// flow: BASE-F114 (hub#1527): in the Hub admin, the confirmation page of «Restore from a copy…» says under the hub the
// size of its database and how long it can stay closed while it is restored — at a phone's, a tablet's and a desktop's
// width, and in Spanish. The page is only opened, never confirmed: `a` stays open for every other spec.
import { expect, type Page, test } from '@playwright/test';

import { ADMIN_PAGE_SIZES, adminPage, CLOSURE_SAID, inControl, staffSession } from './admin-list-helpers';
import { capture, horizontalOverflow } from './helpers';
import { STACK } from './stack';

const KEY = 'RESTORE-CLOSURE';
const HUBS = `http://hubs.localhost:${STACK.hubPort}/admin/control/hub/`;
const ROOT = 'e2e-restore-closure-root';
const CLUSTER = 'e2e-restore';
const CLEAN = [
  'from control.models.hubs import Cluster',
  `Cluster.objects.filter(name="${CLUSTER}", hubs__isnull=True).delete()`,
];

let session = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  // A temporary cluster as the staff registers one: closed to new hubs, holding none.
  session = inControl([
    ...CLEAN,
    'from django.conf import settings',
    'default = settings.DATABASES["default"]',
    `Cluster.objects.get_or_create(name="${CLUSTER}", defaults={"host": default["HOST"], "port": default["PORT"], "pooler_host": "", "is_open": False})`,
    ...staffSession(ROOT),
  ]);
});

test.afterAll(() => {
  inControl(CLEAN);
});

/** Hubs › tick `a` › «Restore from a copy…». */
async function restoreA(page: Page): Promise<void> {
  await page.goto(HUBS);
  const row = page.locator('#result_list tbody tr').filter({ has: page.locator('th.field-slug', { hasText: /^a$/ }) });
  await row.locator('input[name="_selected_action"]').check();
  await page.locator('select[name="action"]').selectOption('restore_from_a_copy');
  await page.locator('button[name="index"]').click();
}

for (const { label, viewport } of ADMIN_PAGE_SIZES) {
  test(`${KEY}: at ${label}, the page says under the hub how long it can stay closed`, async ({ browser }) => {
    const page = await adminPage(browser, session, viewport, 'en');

    await restoreA(page);

    await expect(page.getByRole('heading', { name: 'Restore from a copy' })).toBeVisible();
    await expect(page.locator('fieldset.aligned .help')).toHaveText(CLOSURE_SAID.en);
    await expect(page.locator('#content')).toContainText('The hubs are restored one after another');
    await expect(page.locator('select[name="cluster"] option', { hasText: CLUSTER })).toHaveCount(1);
    // Measured once the page is still (`capture` waits for it): right after loading it read 1 px once.
    await capture(page, `${KEY}-${label}`, { fullPage: true });
    expect(await horizontalOverflow(page), 'the confirmation page asks to be scrolled sideways').toBe(0);
    await page.context().close();
  });
}

test(`${KEY}: in Spanish`, async ({ browser }) => {
  const page = await adminPage(browser, session, { width: 375, height: 667 }, 'es-ES');

  await restoreA(page);

  await expect(page.locator('fieldset.aligned .help')).toHaveText(CLOSURE_SAID.es);
  await expect(page.locator('#content')).toContainText('Los hubs se restauran uno tras otro');
  await capture(page, `${KEY}-375x667-es`, { fullPage: true });
  expect(await horizontalOverflow(page), 'the Spanish page asks to be scrolled sideways').toBe(0);
  await page.context().close();
});
