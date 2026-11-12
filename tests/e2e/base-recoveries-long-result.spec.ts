// flow: BASE-F114 (step 11: Recoveries says how it went) — hub#1308: in the Hub admin, a recovery whose result is long
// (an app's counts, then why it failed, naming its copy's database in one piece, as `base.tenancy.recovery` notes it)
// breaks into several lines inside its cell of Recoveries at a phone's, a tablet's and a desktop's width, and neither
// the page nor the list's box asks to be scrolled sideways.
// The recovery is control's row as the worker leaves a failed one; no copy's database is made: the list only reads it.
import { spawnSync } from 'node:child_process';

import { expect, type Page, test } from '@playwright/test';

import { capture, HUB_DIR, horizontalOverflow } from './helpers';
import { STACK } from './stack';

const KEY = 'BASE-F114-RECOVERIES-LONG-RESULT';
const PLATFORM = `http://hubs.localhost:${STACK.hubPort}`;
const RECOVERIES = `${PLATFORM}/admin/control/copyrecovery/`;
const SIZES = [
  { label: '375', viewport: { width: 375, height: 667 } },
  { label: '768', viewport: { width: 768, height: 1024 } },
  { label: '1280', viewport: { width: 1280, height: 860 } },
];
const ROOT = 'e2e-recoveries-root';

/** Control's side (the registry of hubs, never a business), by `step`: `setup` makes the staff member, the separate copy
 *  of `a` and its failed recovery once, and opens the staff member's session (its key); `clean` drops that copy, its
 *  recovery with it. */
function control(step: 'setup' | 'clean'): string {
  const out = spawnSync(
    'uv',
    [
      'run',
      'python',
      'manage.py',
      'shell',
      '-c',
      [
        'import datetime as dt, uuid',
        'from django.conf import settings',
        'from django.contrib.auth import get_user_model',
        'from django.utils import timezone',
        'from control.models import CopyRecovery, Hub, RestoredCopy',
        `step = "${step}"`,
        'hub = Hub.objects.get(slug="a")',
        `RestoredCopy.objects.filter(hub=hub, asked_by="${ROOT}").delete()`,
        'if step == "setup":',
        '    from django.test import Client',
        '    User = get_user_model()',
        `    root = User.objects.filter(username="${ROOT}").first()`,
        `    root = root or User.objects.create_superuser("${ROOT}", "${ROOT}@example.com", None)`,
        '    now = timezone.now()',
        '    name = f"{settings.DATABASES[\'default\'][\'NAME\']}_copy_{uuid.uuid7().hex}"',
        '    copy = RestoredCopy.objects.create(hub=hub, restore_point=now - dt.timedelta(hours=3), db_name=name, status="made", made_at=now, asked_by=root.username)',
        '    lost = {"app": "customer", "restored": 1, "created": 12, "not_created": 3, "refused": "",',
        '            "reasons": [{"id": str(uuid.uuid7()), "reason": "customer_email_taken"}]}',
        '    error = f"recover_copy_unreadable: The migrator cannot connect to {name!r}: database \\"{name}\\" does not exist"',
        '    CopyRecovery.objects.create(copy=copy, apps=["customer"], status="failed", results=[lost], last_error=error, done_at=now, asked_by=root.username)',
        '    client = Client()',
        '    client.force_login(root)',
        '    print(client.cookies["sessionid"].value)',
        'else:',
        '    print("clean")',
      ].join('\n'),
    ],
    { cwd: HUB_DIR, env: process.env, encoding: 'utf8' },
  );
  if (out.status !== 0) throw new Error(`The shell of manage.py exited with ${out.status}:\n${out.stdout}\n${out.stderr}`);
  return out.stdout.trim().split('\n').at(-1) ?? '';
}

/** How the long result sits: by how many pixels its text runs past its cell and the list's box past its own width
 *  (both 0 when it fits), and on how many lines its text is laid out. */
async function laidOut(page: Page): Promise<{ pastItsCell: number; pastTheList: number; lines: number }> {
  return page.locator('#result_list tbody tr').first().locator('td.field-outcome').evaluate((cell) => {
    const list = cell.closest('.results') as HTMLElement;
    const text = document.createRange();
    text.selectNodeContents(cell);
    const tops = new Set([...text.getClientRects()].map((line) => Math.round(line.top)));
    return {
      pastItsCell: Math.max(0, cell.scrollWidth - cell.clientWidth),
      pastTheList: Math.max(0, list.scrollWidth - list.clientWidth),
      lines: tops.size,
    };
  });
}

// Not serial: each size is measured even when another fails. A worker that starts again after a failure makes its
// rows anew (the setup drops the last ones first).
let session = '';

test.beforeAll(() => {
  session = control('setup');
});

test.afterAll(() => {
  control('clean');
});

for (const { label, viewport } of SIZES) {
  test(`${KEY}: at ${label}, a long result of Recoveries breaks into lines inside its cell, with no sideways scroll`, async ({ browser }) => {
    const context = await browser.newContext({ viewport });
    await context.addCookies([{ name: 'sessionid', value: session, domain: 'hubs.localhost', path: '/' }]);
    const page = await context.newPage();

    await page.goto(RECOVERIES);
    const row = page.locator('#result_list tbody tr').first();
    await expect(row).toContainText('Failed');
    await expect(row.locator('td.field-outcome')).toContainText('Customers: 1 restored, 12 created, 3 not created');
    await expect(row.locator('td.field-outcome')).toContainText('does not exist');
    await capture(page, `${KEY}-${label}`, { fullPage: true });

    // Soft: a failing size says every measure at once. The list's box scrolls by itself (Django's `.results`), so the
    // page alone reads 0 while the result is out of sight: both are measured.
    const sits = await laidOut(page);
    expect.soft(sits.pastItsCell, 'the result runs past its cell').toBe(0);
    expect.soft(sits.pastTheList, 'the list asks to be scrolled sideways').toBe(0);
    expect.soft(await horizontalOverflow(page), 'the page asks to be scrolled sideways').toBe(0);
    expect.soft(sits.lines, 'the long result breaks into several lines').toBeGreaterThan(1);
    await context.close();
  });
}
