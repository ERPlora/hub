// flow: BASE-F114 (steps 6-11), CUSTOMER-F01, CUSTOMER-F07, SERVICE-F01 — hub#1257, hub#1283: in the Hub admin, the
// ERPlora staff choose a separate copy of a business and bring back into it the customers and the services it lost
// since, each created again by its app's own creation (never a copied row). At each size: a card and a service of `a`
// are made; in Hubs, «Restore to a separate copy…» asks a copy of `a` from a temporary cluster (the stack's own server)
// and the worker's pass makes it; the card is deleted in `a` and the service is gone from it; then Separate copies ›
// tick the copy › «Recover into the business…» › Customers and Services ticked (with whatever else answers) ›
// «Recover»; the worker's pass brings them back; Recoveries says «Customers: 1 created» and «Services: 1 created», and
// `a` has the card live again and the service on offer again, each under a new id.
// The stack's worker serves databases only (no moves' thread), so the spec plays its passes, as the specs play the
// relay.
import { spawnSync } from 'node:child_process';

import { expect, type Page, test } from '@playwright/test';

import { capture, HUB_DIR, psql } from './helpers';
import { STACK } from './stack';

const KEY = 'BASE-F114-RECOVER';
const PLATFORM = `http://hubs.localhost:${STACK.hubPort}`;
const COPIES = `${PLATFORM}/admin/control/restoredcopy/`;
const RECOVERIES = `${PLATFORM}/admin/control/copyrecovery/`;
const SIZES = [
  { label: '1440', viewport: { width: 1440, height: 900 } },
  { label: '820', viewport: { width: 820, height: 1180 } },
  { label: '375', viewport: { width: 375, height: 667 } },
];
const HUBS = `${PLATFORM}/admin/control/hub/`;
const TEMPORARY = 'e2e-recover-temporary';
const RUN = Date.now().toString(36);

/** `code` run by `manage.py shell` of this checkout on the stack's database, in `hub`'s own when given (its cards),
 *  else on control (the registry: the separate copy, the staff's session, the worker's pass); its last line. */
function shell(code: string, hub?: string): string {
  const where = hub ? ['--hub', hub] : [];
  const out = spawnSync('uv', ['run', 'python', 'manage.py', 'shell', ...where, '-c', code], {
    cwd: HUB_DIR,
    env: process.env,
    encoding: 'utf8',
  });
  if (out.status !== 0) throw new Error(`The shell of manage.py exited with ${out.status}:\n${out.stdout}\n${out.stderr}`);
  return out.stdout.trim().split('\n').at(-1) ?? '';
}

/** A card of `a` made by Customers' create, as the platform runs an operation in a business; its id. */
function aCard(name: string, email: string): string {
  return shell(
    [
      'from live.context import OperationContext, Scope',
      'from live.operations import get',
      'from control.models import Hub',
      'hub = Hub.objects.get(slug="a")',
      'ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}), language="en")',
      'op = get("customer.customer.create")',
      `print(op(ctx, op.input(name=${JSON.stringify(name)}, email=${JSON.stringify(email)})).id)`,
    ].join('\n'),
    'a',
  );
}

/** A service of `a` made by Services' create, in its first active tax category, as the platform runs an operation in a
 *  business; its id. */
function aService(name: string): string {
  return shell(
    [
      'from live.context import OperationContext, Scope',
      'from live.operations import get',
      'from apps.tax.models import TaxCategory',
      'key = TaxCategory.objects.filter(is_active=True).order_by("key").values_list("key", flat=True).first()',
      'ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}), language="en")',
      'op = get("service.service.create")',
      `print(op(ctx, op.input(name=${JSON.stringify(name)}, price=2500, duration_minutes=45, tax_category_key=key)).id)`,
    ].join('\n'),
    'a',
  );
}

function deleted(card: string): void {
  shell(
    [
      'from live.context import OperationContext, Scope',
      'from live.operations import get',
      'ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}), language="en")',
      'op = get("customer.customer.delete")',
      `op(ctx, op.input(id="${card}"))`,
    ].join('\n'),
    'a',
  );
}

/** Control's side, by `step`: `setup` makes the staff member and the temporary cluster once and opens the staff
 *  member's session (its key), `make` runs the worker's pass of the separate copies (the latest copy of `a`, made),
 *  `recover` runs its pass of the recoveries, and `clean` drops the copies of `a` with their rows and the temporary
 *  cluster. */
function control(step: 'setup' | 'make' | 'recover' | 'clean'): string {
  return shell(
    [
      'from django.contrib.auth import get_user_model',
      'from django.db import connections',
      'from base.tenancy import move, recovery, restore',
      'from control.models import Cluster, Hub, RestoredCopy',
      `step = "${step}"`,
      'User = get_user_model()',
      'root = User.objects.filter(username="e2e-recover-root").first()',
      'root = root or User.objects.create_superuser("e2e-recover-root", "e2e-recover-root@example.com", None)',
      'default = connections.settings["default"]',
      'temporary, _ = Cluster.objects.get_or_create(name=TEMPORARY, defaults={"host": default["HOST"], "port": default["PORT"], "pooler_host": "", "is_open": False})',
      'hub = Hub.objects.get(slug="a")',
      'if step == "setup":',
      '    from django.test import Client',
      '    client = Client()',
      '    client.force_login(root)',
      '    print(client.cookies["sessionid"].value)',
      'elif step == "make":',
      '    restore.run_aside_due(source=lambda copied: copied.db_name)',
      '    made = RestoredCopy.objects.filter(hub=hub).order_by("-asked_at").first()',
      '    assert made.status == "made", made.last_error',
      '    print(made.pk)',
      'elif step == "recover":',
      '    print(recovery.run_due())',
      'else:',
      '    for copy in RestoredCopy.objects.filter(hub=hub, db_name__contains="_copy_"):',
      '        move._drop_copy(copy.db_name, copy.cluster)',
      '        copy.delete()',
      '    Cluster.objects.filter(pk=temporary.pk).delete()',
      '    print("clean")',
    ]
      .join('\n')
      .replace('TEMPORARY', JSON.stringify(TEMPORARY)),
  );
}

async function asStaff(page: Page): Promise<void> {
  await page.context().addCookies([{ name: 'sessionid', value: control('setup'), domain: 'hubs.localhost', path: '/' }]);
}

/** The moment of a copy as the page asks it: now, to the second, in UTC («2026-11-09T14:30:00Z»). */
function now(): string {
  return new Date(Date.now() - 1000).toISOString().replace(/\.\d+Z$/, 'Z');
}

/** The changelist at `url` with the row of `value` ticked and `action` chosen, ready to run. */
async function runOn(page: Page, url: string, value: string, action: string): Promise<void> {
  await page.goto(url);
  const row = page.locator('#result_list tbody tr').filter({ has: page.locator(`input[value="${value}"]`) });
  await row.locator('input[name="_selected_action"]').check();
  await page.locator('select[name="action"]').selectOption(action);
}

test.describe.configure({ mode: 'serial' });

test.afterAll(() => {
  control('clean');
});

for (const { label, viewport } of SIZES) {
  test(`${KEY}: at ${label}, the staff choose a separate copy and the customer and the service the business lost come back`, async ({ browser }) => {
    test.slow();
    const name = `Recovered ${label} ${RUN}`;
    const email = `recovered-${label}-${RUN}@example.com`;
    const card = aCard(name, email);
    const service = aService(name);
    const hubId = psql("select id from base_hub where slug = 'a'");

    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await asStaff(page);

    // Hubs › tick `a` › «Restore to a separate copy…»: the temporary cluster and the moment, then «Make the copies».
    await runOn(page, HUBS, hubId, 'restore_aside');
    await page.locator('button[name="index"]').click();
    await expect(page.getByRole('heading', { name: 'Restore to a separate copy' })).toBeVisible();
    const temporary = page.locator('select[name="cluster"] option', { hasText: TEMPORARY });
    await page.locator('select[name="cluster"]').selectOption((await temporary.getAttribute('value', { timeout: 10_000 })) ?? '');
    await page.locator('input[name="at"]').fill(now());
    await capture(page, `${KEY}-${label}-0-copy-asked`, { fullPage: true });
    await page.locator('input[type="submit"][value="Make the copies"]').click();
    await expect(page.locator('.messagelist .success')).toContainText('1 hub will get a separate copy');
    const copy = control('make');
    // Lost since: the card deleted in the business.
    deleted(card);
    expect(psql(`select count(*) from customer_customer where email = '${email}' and deleted_at is null`)).toBe('0');
    // And the service gone from the business altogether: no operation deletes one (it is archived), a lost database does.
    psql(`delete from service_service where id = '${service}'`);
    expect(psql(`select count(*) from service_service where name = '${name}'`)).toBe('0');

    // Separate copies › tick the copy › «Recover into the business…».
    await runOn(page, COPIES, copy, 'recover_into_the_business');
    await expect(page.locator('#result_list tbody tr').filter({ has: page.locator(`input[value="${copy}"]`) })).toContainText('Made');
    await capture(page, `${KEY}-${label}-1-copies`);
    await page.locator('button[name="index"]').click();

    // The confirmation page: what comes back, ticked, and the button.
    await expect(page.getByRole('heading', { name: 'Recover into the business' })).toBeVisible();
    await expect(page.locator('input[name="apps"][value="customer"]')).toBeChecked();
    await expect(page.locator('input[name="apps"][value="service"]')).toBeChecked();
    await expect(page.getByText('nothing is ever copied', { exact: false })).toBeVisible();
    await capture(page, `${KEY}-${label}-2-confirm`, { fullPage: true });
    await page.locator('input[type="submit"][value="Recover"]').click();

    // What else answers (another app's recovery) may sit between them, in the apps' order.
    await expect(page.locator('.messagelist .success')).toContainText(
      /1 separate copy will give back Customers, (.+, )?Services(, .+)? into its business within a few minutes/,
    );
    await capture(page, `${KEY}-${label}-3-asked`);

    // The worker's pass, then Recoveries says what came back.
    expect(control('recover')).toBe('1');
    await page.goto(RECOVERIES);
    const recovered = page.locator('#result_list tbody tr').first();
    await expect(recovered).toContainText('Done');
    await expect(recovered).toContainText('Customers: 1 created');
    await expect(recovered).toContainText('Services: 1 created');
    await capture(page, `${KEY}-${label}-4-recoveries`, { fullPage: true });
    await recovered.locator('a').first().click();
    await expect(page.locator('.field-what .readonly')).toHaveText(/^Customers, (.+, )?Services(, .+)?$/);
    await capture(page, `${KEY}-${label}-5-recovery`, { fullPage: true });

    // In the business, the card is live again, a new one made by Customers' create; the deleted one stays deleted.
    expect(psql(`select count(*) from customer_customer where email = '${email}' and deleted_at is null`)).toBe('1');
    expect(psql(`select id from customer_customer where email = '${email}' and deleted_at is null`)).not.toBe(card);
    expect(psql(`select name from customer_customer where id = '${card}' and deleted_at is not null`)).toBe(name);
    // And the service on offer again, a new one made by Services' create, with what it had.
    expect(psql(`select price, duration_minutes, is_active from service_service where name = '${name}'`)).toBe('2500|45|t');
    expect(psql(`select id from service_service where name = '${name}'`)).not.toBe(service);
    await context.close();
  });
}
