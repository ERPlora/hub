// flow: BASE-F114 (step 8: Separate copies lists each copy with its moment, until when it is kept and why it could not be
// made) — hub#1345: in the Hub admin, Separate copies shows each copy whole at a phone's, two tablets' and a desktop's
// width (its business and moment on two lines, its state, until when it is kept and its last error), a long last error
// (naming the copy's database in one piece, as `base.tenancy.restore` notes it) breaks into several lines inside its
// cell, the filter goes under the list up to the tablet's width and the actions fit inside the list's width; neither the
// page nor the list's box asks to be scrolled sideways. In English and in Spanish, whose column headers are longer
// («se guarda hasta»).
// The copies are control's rows as the worker leaves a made one and a failed one; no database is made: the list only
// reads them.
import { expect, type Page, test } from '@playwright/test';

import { ADMIN_LIST_SIZES, adminPage, expectBrokenInItsCell, inControl, staffSession } from './admin-list-helpers';
import { capture } from './helpers';
import { STACK } from './stack';

const KEY = 'BASE-F114-COPIES-ASIDE-LONG-ERROR';
const PLATFORM = `http://hubs.localhost:${STACK.hubPort}`;
const COPIES = `${PLATFORM}/admin/control/restoredcopy/`;
const ROOT = 'e2e-copies-aside-root';
/** Up to Django's tablet width the filter goes under the list (control/static/control/admin.css). */
const FILTER_UNDER_UP_TO = 1024;
/** The admin speaks the browser's language (Django's LocaleMiddleware reads its Accept-Language). */
const LANGUAGES = ['en', 'es'];
/** Drops the separate copies of `a` this spec made. */
const DROP = [
  'from control.models import Hub, RestoredCopy',
  'hub = Hub.objects.get(slug="a")',
  `RestoredCopy.objects.filter(hub=hub, asked_by="${ROOT}").delete()`,
];

/** Where the filter and the actions sit against the list's box: whether the filter is under it or beside it, and by how
 *  many pixels the actions' bar (its menu and its button) runs past the box's right edge or past its own width. */
async function around(page: Page): Promise<{ filterUnder: boolean; filterBeside: boolean; actionsPast: number }> {
  return page.evaluate(() => {
    const list = (document.querySelector('#result_list') as HTMLElement).closest('.results') as HTMLElement;
    const filter = document.querySelector('#changelist-filter') as HTMLElement;
    const actions = document.querySelector('#changelist-form .actions') as HTMLElement;
    const box = list.getBoundingClientRect();
    const sits = filter.getBoundingClientRect();
    const rightmost = Math.max(...[...actions.querySelectorAll('select, button')].map((it) => it.getBoundingClientRect().right));
    return {
      filterUnder: sits.top >= box.bottom - 1,
      filterBeside: sits.left >= box.right - 1,
      actionsPast: Math.max(0, Math.ceil(rightmost - box.right), actions.scrollWidth - actions.clientWidth),
    };
  });
}

// Not serial: each size is measured even when another fails. A worker that starts again after a failure makes its
// rows anew (the setup drops the last ones first).
let session = '';

test.beforeAll(() => {
  // Two separate copies of `a`, one made and one that could not be made, and the staff member's session.
  session = inControl([
    'import datetime as dt, uuid',
    'from django.conf import settings',
    'from django.utils import timezone',
    ...DROP,
    'now = timezone.now()',
    'control_db = settings.DATABASES["default"]["NAME"]',
    'made = f"{control_db}_copy_{uuid.uuid7().hex}"',
    `RestoredCopy.objects.create(hub=hub, restore_point=now - dt.timedelta(days=1), db_name=made, status="made", made_at=now, asked_by="${ROOT}")`,
    'name = f"{control_db}_copy_{uuid.uuid7().hex}"',
    'error = f"restore_aside_restore_failed: pg_restore into {name} failed (exit 1): pg_restore: error: connection to server failed: FATAL: database \\"{name}\\" does not exist"',
    `RestoredCopy.objects.create(hub=hub, restore_point=now - dt.timedelta(hours=3), db_name=name, status="failed", last_error=error, asked_by="${ROOT}")`,
    ...staffSession(ROOT),
  ]);
});

test.afterAll(() => {
  inControl(DROP);
});

for (const { label, viewport } of ADMIN_LIST_SIZES) for (const language of LANGUAGES) {
  test(`${KEY}: at ${label} in ${language}, Separate copies shows each copy whole and breaks a long last error inside its cell, with no sideways scroll`, async ({ browser }) => {
    const page = await adminPage(browser, session, viewport, language);

    await page.goto(COPIES);
    await expect(page.locator('html')).toHaveAttribute('lang', language);
    const rows = page.locator('#result_list tbody tr');
    const failed = rows.filter({ has: page.locator('td.field-last_error', { hasText: 'restore_aside_restore_failed' }) });
    const made = rows.filter({ has: page.locator('td.field-kept_until', { hasText: 'UTC' }) });
    await expect(failed).toHaveCount(1);
    await expect(made).toHaveCount(1);
    await expect(failed.locator('.field-made_from')).toContainText('UTC');
    await capture(page, `${KEY}-${label}-${language}`, { fullPage: true });

    await expectBrokenInItsCell(page, failed, 'last_error', 'the last error');
    const next = await around(page);
    if (viewport.width <= FILTER_UNDER_UP_TO) {
      expect.soft(next.filterUnder, 'the filter is under the list').toBe(true);
    } else {
      expect.soft(next.filterBeside, 'the filter is beside the list').toBe(true);
    }
    expect.soft(next.actionsPast, 'the actions run past the list').toBe(0);
    await page.context().close();
  });
}
