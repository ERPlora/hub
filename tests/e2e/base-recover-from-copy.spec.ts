// flow: BASE-F114 (steps 6-11), CUSTOMER-F07, CUSTOMER-F33, CUSTOMER-F06, CUSTOMER-F04, INVENTORY-F01, INVENTORY-F04,
// INVENTORY-F07, INVENTORY-F08, INVENTORY-F34, SERVICE-F01, SERVICE-F07, SERVICE-F31, APPOINTMENT-F11: in the Hub
// admin, the ERPlora staff choose a separate copy of a business and bring back into it the customers, the products, the
// services and the appointments it lost since, by their apps' own operations (never a copied row): a card, a product or
// an appointment the business deleted and still holds comes back the same, with its history (the card with its group),
// by Customers', Inventory's and Appointments' restore; a card it no longer has at all comes back as a new one with its
// group (the business's own of that name), its tag (made again: the business deleted it) and its custom field's value;
// a product category and a service category the business deleted come back as new ones, before what goes in them, the
// product category with the product the business kept live put back in it by Inventory's link; and a service as a new
// one, made by Services' create, into its category, and assigned by Services' assign to the professional who performed
// it, with her own minutes and price, never to the one Staff terminated since, whom Recoveries names with why. At each
// size: two cards in a group, the second with a tag and a custom field's
// value, two products in their own category, a service in its own category, performed by two professionals of Staff, and
// an appointment of another card with its own professional of `a` are made; in Hubs, «Restore to a separate copy…»
// asks a copy of `a` from a temporary cluster (the stack's own server) and the worker's pass makes it; the first card,
// the first product, the products' category, the service's category and the appointment are deleted in `a`, the second
// professional is terminated, the second
// card, the tag and the service are gone from it; then Separate copies › tick the copy › «Recover into the business…» ›
// Customers, Products, Services and Appointments ticked (with whatever else answers) › «Recover»; the worker's pass
// brings them back; Recoveries says how each thing came back, apart: «Customers: 1 restored, 1 created», «Product
// categories: 1 created; Products: 1 restored; Product links to categories: 1 created» (the kept product's link),
// «Service categories: 1 created; Services: 1 created, 1 with notes» and «Appointments: 1 restored; Repeating
// appointments: 0 created» (its series did not change), and its page notes that the service came back without the
// terminated professional, and why; and `a` has the same card live
// again in its group, the second one again in that group with its tag and its value, the same product live again in
// its category back under a new id, the kept product in it again, the same appointment (its number, its history
// ending in «restored») live again, and the service category and the service live again under new ids, the service in
// that category and performed by that professional again; in its Agenda, the appointment's «History» ends in
// «Restored» (APPOINTMENT-F10).
// The stack's worker serves databases only (no moves' thread), so the spec plays its passes, as the specs play the
// relay.
import { spawnSync } from 'node:child_process';

import { expect, type Page, test } from '@playwright/test';

import { capture, HUB_DIR, psql } from './helpers';
import { ownerPage, rowAction } from './service-helpers';
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

/** `operation` run in `a` with `input`, as the platform runs an operation in a business; what it answers's id. */
function inA(operation: string, input: Record<string, unknown>): string {
  return shell(
    [
      'import json',
      'from live.context import OperationContext, Scope',
      'from live.operations import get',
      'ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}), language="en")',
      `op = get(${JSON.stringify(operation)})`,
      `print(getattr(op(ctx, op.input(**json.loads(${JSON.stringify(JSON.stringify(input))}))), "id", ""))`,
    ].join('\n'),
    'a',
  );
}

/** A card of `a` made by Customers' create; its id. */
function aCard(name: string, email: string): string {
  return inA('customer.customer.create', { name, email });
}

/** The key of the first active tax category of `a`. */
function aTaxKey(): string {
  return shell('from apps.tax.models import TaxCategory\nprint(TaxCategory.objects.filter(is_active=True).order_by("key").first().key)', 'a');
}

/** A product of `a` made by Inventory's create, in `category`, with the first active tax category of `a`; its id. */
function aProduct(name: string, sku: string, category: string): string {
  return inA('inventory.product.create', { name, sku, price: 250, tax_category_key: aTaxKey(), category_ids: [category] });
}

/** A service of `a` made by Services' create, in `category`, with the first active tax category of `a`; its id. */
function aService(name: string, category: string): string {
  return inA('service.service.create', {
    name,
    price: 2500,
    duration_minutes: 45,
    category_id: category,
    tax_category_key: aTaxKey(),
  });
}

/** A Monday one to two weeks ahead at `hhmm` on the business's wall clock (open by default, never in the past). */
function aMondayAt(hhmm: string): string {
  const day = new Date();
  day.setDate(day.getDate() + ((8 - day.getDay()) % 7) + 7);
  const date = [day.getFullYear(), String(day.getMonth() + 1).padStart(2, '0'), String(day.getDate()).padStart(2, '0')];
  return `${date.join('-')}T${hhmm}`;
}

/** An appointment of `a` booked by the agenda's create for a card of its own, with a professional and a service of its
 *  own (no category: the spec's category is deleted); its id. */
function anAppointment(label: string): string {
  const customer = aCard(`Booked ${label} ${RUN}`, `booked-${label}-${RUN}@example.com`);
  const staff = inA('staff.member.create', { first_name: 'Booked', last_name: `${label} ${RUN}` });
  const service = inA('service.service.create', {
    name: `Cut ${label} ${RUN}`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: aTaxKey(),
  });
  return inA('appointment.appointment.create', {
    customer_id: customer,
    staff_id: staff,
    services: [{ service_id: service }],
    start: aMondayAt('10:00'),
  });
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
  test(`${KEY}: at ${label}, the staff choose a separate copy and the customer, the product, the service and the appointment the business lost come back`, async ({ browser }) => {
    test.slow();
    const name = `Recovered ${label} ${RUN}`;
    const email = `recovered-${label}-${RUN}@example.com`;
    const card = aCard(name, email);
    // What hangs from the cards: a group both are in, and a tag and a custom field's value of the second.
    const group = inA('customer.group.create', { name: `VIP ${label} ${RUN}` });
    const tagName = `Regular ${label} ${RUN}`;
    const tag = inA('customer.tag.create', { name: tagName, color: 'success' });
    const field = inA('customer.field.create', { name: `Size ${label} ${RUN}` });
    const goneEmail = `gone-${label}-${RUN}@example.com`;
    const goneCard = aCard(`Gone ${label} ${RUN}`, goneEmail);
    inA('customer.customer.set_groups', { id: card, group_ids: [group] });
    inA('customer.customer.set_groups', { id: goneCard, group_ids: [group] });
    inA('customer.customer.set_tags', { id: goneCard, tag_ids: [tag] });
    inA('customer.customer.update', { id: goneCard, field_values: [{ field_id: field, value: 'M' }] });
    const sku = `REC-${label}-${RUN}`;
    const shelf = inA('inventory.category.create', { name, color: '#33aa66' });
    const product = aProduct(name, sku, shelf);
    // Kept live by the business: deleting the category takes it out of it.
    const kept = aProduct(`Kept ${label} ${RUN}`, `KEPT-${label}-${RUN}`, shelf);
    const category = inA('service.category.create', { name, color: '#cc0066' });
    const service = aService(name, category);
    const professional = inA('staff.member.create', { first_name: 'Recovered', last_name: `${label} ${RUN}` });
    inA('service.assignment.assign', { service_id: service, member_id: professional, custom_duration: 50, custom_price: 2800 });
    // And one who performed it too and leaves the business before it comes back.
    const leaving = inA('staff.member.create', { first_name: 'Leaving', last_name: `${label} ${RUN}` });
    inA('service.assignment.assign', { service_id: service, member_id: leaving });
    const appointment = anAppointment(label);
    const number = psql(`select number from appointment_appointment where id = '${appointment}'`);
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
    // Lost since: the card, the product, the product's category and the service's category deleted in the business.
    inA('customer.customer.delete', { id: card });
    inA('inventory.product.delete', { id: product });
    inA('inventory.category.delete', { id: shelf });
    inA('service.category.delete', { id: category });
    inA('appointment.appointment.delete', { id: appointment });
    inA('staff.member.terminate', { id: leaving });
    expect(psql(`select count(*) from customer_customer where email = '${email}' and deleted_at is null`)).toBe('0');
    expect(psql(`select count(*) from inventory_product where sku = '${sku}' and not is_deleted`)).toBe('0');
    expect(psql(`select count(*) from inventory_productcategory where product_id = '${kept}'`)).toBe('0');
    // The second card gone from the business altogether, with what hung from it (a lost database, or the Hub admin's
    // «Delete»), and the tag deleted by Customers' own operation.
    for (const table of ['customer_customer_groups', 'customer_customer_tags', 'customer_customfieldvalue']) {
      psql(`delete from ${table} where customer_id = '${goneCard}'`);
    }
    psql(`delete from customer_customer where id = '${goneCard}'`);
    inA('customer.tag.delete', { id: tag });
    expect(psql(`select count(*) from customer_customertag where name = '${tagName}'`)).toBe('0');
    // And the service gone from the business altogether, who performed it with it: no operation deletes one (it is
    // archived), a lost database does.
    psql(`delete from service_assignment where service_id = '${service}'`);
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
    await expect(page.locator('input[name="apps"][value="inventory"]')).toBeChecked();
    await expect(page.locator('input[name="apps"][value="service"]')).toBeChecked();
    await expect(page.locator('input[name="apps"][value="appointment"]')).toBeChecked();
    await expect(page.getByText('nothing is ever copied', { exact: false })).toBeVisible();
    await expect(page.getByText('comes back as it was, with its history', { exact: false })).toBeVisible();
    await capture(page, `${KEY}-${label}-2-confirm`, { fullPage: true });
    await page.locator('input[type="submit"][value="Recover"]').click();

    // What else answers (another app's recovery) may sit among them, in the apps' order.
    await expect(page.locator('.messagelist .success')).toContainText(
      /1 separate copy will give back (.+, )?Customers, (.+, )?Products, (.+, )?Services(, .+)? into its business within a few minutes/,
    );
    await capture(page, `${KEY}-${label}-3-asked`);

    // The worker's pass, then Recoveries says what came back.
    expect(control('recover')).toBe('1');
    await page.goto(RECOVERIES);
    const recovered = page.locator('#result_list tbody tr').first();
    await expect(recovered).toContainText('Done');
    await expect(recovered).toContainText('Customers: 1 restored, 1 created');
    await expect(recovered).toContainText(
      'Product categories: 1 created; Products: 1 restored; Product links to categories: 1 created',
    );
    // The service came back without the professional Staff terminated: counted, and said on its page.
    await expect(recovered).toContainText('Service categories: 1 created; Services: 1 created, 1 with notes');
    await expect(recovered).toContainText('Appointments: 1 restored; Repeating appointments: 0 created');
    await capture(page, `${KEY}-${label}-4-recoveries`, { fullPage: true });
    await recovered.locator('a').first().click();
    await expect(page.locator('.field-what .readonly')).toHaveText(/^(.+, )?Customers, (.+, )?Products, (.+, )?Services(, .+)?$/);
    await expect(page.locator('.field-notes .readonly li')).toHaveText([
      `${service}: service.member_terminated: came back without the professional ${leaving}: terminated in Staff`,
    ]);
    await capture(page, `${KEY}-${label}-5-recovery`, { fullPage: true });

    // In the business, the same card is live again, by Customers' restore, and no new one was made.
    expect(psql(`select id from customer_customer where email = '${email}' and deleted_at is null`)).toBe(card);
    expect(psql(`select count(*) from customer_customer where email = '${email}'`)).toBe('1');
    // In its group still: deleting kept it.
    expect(psql(`select count(*) from customer_customer_groups where customer_id = '${card}' and customergroup_id = '${group}'`)).toBe('1');
    // The second card, a new one by Customers' own operations, in the same group (never a second one of that name), with
    // its tag made again as it was and its value.
    const again = psql(`select id from customer_customer where email = '${goneEmail}' and deleted_at is null`);
    expect(again).not.toBe('');
    expect(again).not.toBe(goneCard);
    expect(psql(`select count(*) from customer_customer_groups where customer_id = '${again}' and customergroup_id = '${group}'`)).toBe('1');
    expect(psql(`select count(*) from customer_customergroup where name = 'VIP ${label} ${RUN}'`)).toBe('1');
    expect(psql(`select t.name || '|' || t.color from customer_customer_tags m join customer_customertag t on t.id = m.customertag_id where m.customer_id = '${again}'`)).toBe(`${tagName}|success`);
    expect(psql(`select value from customer_customfieldvalue where customer_id = '${again}' and field_id = '${field}'`)).toBe('M');
    // And the same product is live again, by Inventory's restore, and no new one was made.
    expect(psql(`select id from inventory_product where sku = '${sku}' and not is_deleted`)).toBe(product);
    expect(psql(`select count(*) from inventory_product where sku = '${sku}'`)).toBe('1');
    // In its category, back before it: a new one, made by Categories' create, with its colour; the deleted one stays
    // deleted.
    const shelfBack = psql(`select id from inventory_category where name = '${name}' and not is_deleted`);
    expect(shelfBack).not.toBe(shelf);
    expect(psql(`select color from inventory_category where id = '${shelfBack}'`)).toBe('#33aa66');
    expect(psql(`select category_id from inventory_productcategory where product_id = '${product}'`)).toBe(shelfBack);
    expect(psql(`select is_deleted from inventory_category where id = '${shelf}'`)).toBe('t');
    // And the product the business kept live, back in it by Inventory's link, the same product.
    expect(psql(`select category_id from inventory_productcategory where product_id = '${kept}'`)).toBe(shelfBack);
    // And the service on offer again, a new one made by Services' create, with what it had, in its category brought
    // back before it: a new one, made by Categories' create; the deleted one stays deleted.
    expect(psql(`select price, duration_minutes, is_active from service_service where name = '${name}'`)).toBe('2500|45|t');
    expect(psql(`select id from service_service where name = '${name}'`)).not.toBe(service);
    const back = psql(`select id from service_category where name = '${name}' and not is_deleted`);
    expect(back).not.toBe(category);
    expect(psql(`select color from service_category where id = '${back}'`)).toBe('#cc0066');
    expect(psql(`select category_id from service_service where name = '${name}'`)).toBe(back);
    expect(psql(`select is_deleted from service_category where id = '${category}'`)).toBe('t');
    // And performed again by the same professional, with her own minutes and price, by Services' assign.
    const performer = `select member_id, custom_duration, custom_price, is_active from service_assignment where service_id = (select id from service_service where name = '${name}')`;
    expect(psql(performer)).toBe(`${professional}|50|2800|t`);
    // And the same appointment on the agenda again, by Appointments' restore: its number, its history ending in
    // «restored», and no new one booked for its card.
    expect(psql(`select number, deleted_at is null from appointment_appointment where id = '${appointment}'`)).toBe(`${number}|t`);
    expect(psql(`select action from appointment_history where appointment_id = '${appointment}' order by at desc, id desc limit 1`)).toBe('restored');
    expect(psql(`select count(*) from appointment_appointment where customer_name = 'Booked ${label} ${RUN}'`)).toBe('1');
    await context.close();

    // In the business's Agenda, its «History» keeps its lines and ends in «Restored» (APPOINTMENT-F10). The system booked
    // and deleted it and the recovery brought it back: each line says the platform did it, never its internal mark.
    const agenda = await ownerPage(browser, `/appointment/agenda?date=${aMondayAt('10:00').slice(0, 10)}`, viewport);
    await rowAction(agenda.page, 'appointment-list', appointment, 'history');
    const history = agenda.page.locator('ion-modal[data-testid=appointment-history-modal]');
    await expect(history.locator('[data-testid=appointment-history-entry]')).toHaveText([
      /^Booked.* · Done by the platform$/,
      /^Deleted.* · Done by the platform$/,
      /^Restored.* · Done by the platform$/,
    ]);
    await capture(agenda.page, `${KEY}-${label}-6-history`);
    await agenda.context.close();
  });
}
