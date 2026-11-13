// flow: BASE-F114 (step 11: Recoveries says how it went) — hub#1308: in the Hub admin, a recovery whose result is long
// (an app's counts, then why it failed, naming its copy's database in one piece, as `base.tenancy.recovery` notes it)
// breaks into several lines inside its cell of Recoveries at a phone's, two tablets' and a desktop's width, and neither
// the page nor the list's box asks to be scrolled sideways.
// The recovery is control's row as the worker leaves a failed one; no copy's database is made: the list only reads it.
import { expect, test } from '@playwright/test';

import { ADMIN_LIST_SIZES, adminPage, expectBrokenInItsCell, inControl, staffSession } from './admin-list-helpers';
import { capture } from './helpers';
import { STACK } from './stack';

const KEY = 'BASE-F114-RECOVERIES-LONG-RESULT';
const PLATFORM = `http://hubs.localhost:${STACK.hubPort}`;
const RECOVERIES = `${PLATFORM}/admin/control/copyrecovery/`;
const ROOT = 'e2e-recoveries-root';
/** Drops the separate copy of `a` this spec made, its recovery with it. */
const DROP = [
  'from control.models import CopyRecovery, Hub, RestoredCopy',
  'hub = Hub.objects.get(slug="a")',
  `RestoredCopy.objects.filter(hub=hub, asked_by="${ROOT}").delete()`,
];

// Not serial: each size is measured even when another fails. A worker that starts again after a failure makes its
// rows anew (the setup drops the last ones first).
let session = '';

test.beforeAll(() => {
  // The separate copy of `a` and its failed recovery, and the staff member's session.
  session = inControl([
    'import datetime as dt, uuid',
    'from django.conf import settings',
    'from django.utils import timezone',
    ...DROP,
    'now = timezone.now()',
    'name = f"{settings.DATABASES[\'default\'][\'NAME\']}_copy_{uuid.uuid7().hex}"',
    `copy = RestoredCopy.objects.create(hub=hub, restore_point=now - dt.timedelta(hours=3), db_name=name, status="made", made_at=now, asked_by="${ROOT}")`,
    'lost = {"app": "customer", "restored": 1, "created": 12, "not_created": 3, "refused": "",',
    '        "reasons": [{"id": str(uuid.uuid7()), "reason": "customer.phone_invalid: This phone is not valid."}]}',
    'error = f"recover_copy_unreadable: The migrator cannot connect to {name!r}: database \\"{name}\\" does not exist"',
    `CopyRecovery.objects.create(copy=copy, apps=["customer"], status="failed", results=[lost], last_error=error, done_at=now, asked_by="${ROOT}")`,
    ...staffSession(ROOT),
  ]);
});

test.afterAll(() => {
  inControl(DROP);
});

for (const { label, viewport } of ADMIN_LIST_SIZES) {
  test(`${KEY}: at ${label}, a long result of Recoveries breaks into lines inside its cell, with no sideways scroll`, async ({ browser }) => {
    const page = await adminPage(browser, session, viewport);

    await page.goto(RECOVERIES);
    const row = page.locator('#result_list tbody tr').first();
    await expect(row).toContainText('Failed');
    await expect(row.locator('td.field-outcome')).toContainText('Customers: 1 restored, 12 created, 3 not created');
    await expect(row.locator('td.field-outcome')).toContainText('does not exist');
    await capture(page, `${KEY}-${label}`, { fullPage: true });

    await expectBrokenInItsCell(page, row, 'outcome', 'the result');
    await page.context().close();
  });
}
