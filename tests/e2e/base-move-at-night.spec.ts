// flow: ninguno — operación de plataforma (hub#1508, part of hub#931): in the Hub admin, «Move to cluster…» asks when,
// with the business's next night first; asked so, the business stays open, the hubs' list says where and when it goes on
// the business's own clock, and «Cancel the move» takes it away — at a phone's, a tablet's and a desktop's width, and
// the confirmation page in Spanish too. The e2e stack's worker makes databases only: nothing starts the move.
import { expect, type Page, test } from '@playwright/test';

import { adminPage, inControl, staffSession } from './admin-list-helpers';
import { capture, horizontalOverflow } from './helpers';
import { STACK } from './stack';

const KEY = 'MOVE-AT-NIGHT';
const PLATFORM = `http://hubs.localhost:${STACK.hubPort}`;
const HUBS = `${PLATFORM}/admin/control/hub/`;
const ROOT = 'e2e-move-at-night-root';
const CLUSTER = 'e2e-night';
const SIZES = [
  { label: '375x667', viewport: { width: 375, height: 667 } },
  { label: '820x1180', viewport: { width: 820, height: 1180 } },
  { label: '1440x900', viewport: { width: 1440, height: 900 } },
];
/** Takes away a move of `a` asked for the night to the spec's cluster. */
const UNSCHEDULE = [
  'from control.models import Cluster, Hub',
  `Hub.objects.filter(slug="a", move_scheduled_to__name="${CLUSTER}").update(move_scheduled_to=None, move_scheduled_for=None)`,
];
/** And then the spec's cluster, once no hub points at it. */
const CLEAN = [
  ...UNSCHEDULE,
  `Cluster.objects.filter(name="${CLUSTER}", hubs__isnull=True, incoming__isnull=True, scheduled_incoming__isnull=True).delete()`,
];

let session = '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  // An open cluster on the stack's own server, and the staff member's session.
  session = inControl([
    ...CLEAN,
    'from django.conf import settings',
    'default = settings.DATABASES["default"]',
    `Cluster.objects.get_or_create(name="${CLUSTER}", defaults={"host": default["HOST"], "port": default["PORT"], "pooler_host": "", "is_open": True})`,
    ...staffSession(ROOT),
  ]);
});

test.afterAll(() => {
  inControl(CLEAN);
});

/** Hubs › tick `a` › run `action`. */
async function runOnA(page: Page, action: string): Promise<void> {
  await page.goto(HUBS);
  const row = page.locator('#result_list tbody tr').filter({ has: page.locator('th.field-slug', { hasText: /^a$/ }) });
  await row.locator('input[name="_selected_action"]').check();
  await page.locator('select[name="action"]').selectOption(action);
  await page.locator('button[name="index"]').click();
}

function rowOfA(page: Page) {
  return page.locator('#result_list tbody tr').filter({ has: page.locator('th.field-slug', { hasText: /^a$/ }) });
}

for (const { label, viewport } of SIZES) {
  test(`${KEY}: at ${label}, a move asked for the business's night leaves it open, says when, and is cancelled`, async ({ browser }) => {
    inControl(UNSCHEDULE);
    const page = await adminPage(browser, session, viewport, 'en');

    await runOnA(page, 'move_to_cluster');
    await expect(page.getByRole('heading', { name: 'Move to cluster' })).toBeVisible();
    await expect(page.getByLabel("In its next night, between 03:00 and 05:00 of the business's time")).toBeChecked();
    await expect(page.getByLabel('Now', { exact: true })).not.toBeChecked();
    const target = page.locator('select[name="cluster"] option', { hasText: CLUSTER });
    await page.locator('select[name="cluster"]').selectOption((await target.getAttribute('value', { timeout: 10_000 })) ?? '');
    expect(await horizontalOverflow(page), 'the confirmation page asks to be scrolled sideways').toBe(0);
    await capture(page, `${KEY}-${label}-1-asked`, { fullPage: true });

    await page.locator('input[type="submit"][value="Move them"]').click();
    await expect(page.locator('.messagelist .success')).toContainText(
      `1 hub will move to ${CLUSTER} in its next night, starting between 03:00 and 05:00 on its own clock`,
    );
    await expect(rowOfA(page).locator('td.field-on_cluster')).toContainText(
      new RegExp(`\\(to ${CLUSTER} at \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2} \\S+\\)`),
    );
    // Open meanwhile: its host answers as ever (to its login), never 503 «maintenance».
    const host = await page.request.get(`${STACK.hub('a')}/`, { maxRedirects: 0 });
    expect(host.status(), 'the business is open until its night').not.toBe(503);
    await capture(page, `${KEY}-${label}-2-scheduled`, { fullPage: true });

    await runOnA(page, 'cancel_the_move');
    await expect(page.locator('.messagelist .success')).toContainText(
      '1 move asked for the night was cancelled: the hub stays where it is, open.',
    );
    await expect(rowOfA(page).locator('td.field-on_cluster')).not.toContainText(CLUSTER);
    await capture(page, `${KEY}-${label}-3-cancelled`, { fullPage: true });
    await page.context().close();
  });
}

test(`${KEY}: its confirmation page speaks Spanish`, async ({ browser }) => {
  const page = await adminPage(browser, session, { width: 375, height: 667 }, 'es-ES');

  await runOnA(page, 'move_to_cluster');

  await expect(page.getByLabel('En su próxima madrugada, entre las 03:00 y las 05:00 de la hora del negocio')).toBeChecked();
  await expect(page.getByLabel('Ahora', { exact: true })).not.toBeChecked();
  expect(await horizontalOverflow(page), 'the Spanish page asks to be scrolled sideways').toBe(0);
  await capture(page, `${KEY}-375x667-es`, { fullPage: true });
  await page.context().close();
});
