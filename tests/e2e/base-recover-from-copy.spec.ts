// flow: BASE-F114 (steps 6-11), CUSTOMER-F07, CUSTOMER-F33, CUSTOMER-F06, CUSTOMER-F04, INVENTORY-F01, INVENTORY-F04,
// INVENTORY-F07, INVENTORY-F08, INVENTORY-F34, SERVICE-F01, SERVICE-F07, SERVICE-F08, SERVICE-F31, APPOINTMENT-F11,
// PRICING-F14, PRICING-F15, MODIFIER-F10, COMBO-F15: in the Hub
// admin, the ERPlora staff choose a separate copy of a business and bring back into it the customers, the products, the
// services and the appointments it lost since, by their apps' own operations (never a copied row): a card, a product or
// an appointment the business deleted and still holds comes back the same, with its history (the card with its group),
// by Customers', Inventory's and Appointments' restore; a card it no longer has at all comes back as a new one with its
// group (the business's own of that name), its tag (made again: the business deleted it) and its custom field's value;
// a product category and a service category the business deleted come back as new ones, before what goes in them, the
// product category with the product the business kept live put back in it by Inventory's link, the service category
// with the service the business kept without a category and the subcategory it kept at the root put back in it by
// Services' links, never the service it moved since, which Recoveries names with why; and a service as a new
// one, made by Services' create, into its category, and assigned by Services' assign to the professional who performed
// it, with her own minutes and price, never to the one Staff terminated since, whom Recoveries names with why; the
// deleted product's price in a price list comes back too, put again by Price Lists' add, the modifier group it asked
// for, linked again by Modifiers' attach, with the option the business took away from that group it keeps added again
// by Modifiers, as the modifier group its category asked for is to the category brought back
// (that group, which the business deleted with its option, made again first by Modifiers with its option), and the
// menu it was offered in, which the business withdrew with its course: made again by Menus with that course and its
// choice of the product, with its supplement.
// At each size: two cards in a group, the second with a tag and a custom field's value, two products in their own
// category asking for a modifier group of its own, the first priced in a price list of its own, asking for a modifier
// group of its own and offered as a main in a menu of its own, a service in its own category with a subcategory,
// performed by two professionals of Staff, and an appointment of another card with its own professional of `a` are
// made; in Hubs, «Restore to a separate copy…»
// asks a copy of `a` from a temporary cluster (the stack's own server) and the worker's pass makes it; the first card,
// the first product (its price, its group and its choice taken away, as the relay hands its deletion to Price Lists,
// Modifiers and Menus, then the option taken away from its group, and then the menu withdrawn with its course),
// the products' category (its group taken away too, and then that group deleted with its option), the
// service's category and the appointment are deleted in `a`, the second professional is terminated, the second
// card, the tag and the service are gone from it; then Separate copies › tick the copy › «Recover into the business…» ›
// Customers, Products, Services and Appointments ticked (with whatever else answers) › «Recover»; the worker's pass
// brings them back; Recoveries says how each thing came back, apart: «Customers: 1 restored, 1 created», «Product
// categories: 1 created; Products: 1 restored; Product links to categories: 1 created» (the kept product's link),
// «Service categories: 1 created, 1 with notes; Services: 1 created, 1 with notes; Service links to categories:
// 1 created; Subcategory links to categories: 1 created» (the kept service and subcategory) and «Appointments: 1
// restored; Repeating appointments: 0 created» (its series did not change), «Price list prices: 1 created», «Menus:
// 1 created; Menu courses: 1 created; Menu choices of products: 1 created» and «Modifier groups: 1 created; Modifier
// options: 1 created; Modifier groups of categories: 1 created; Modifier groups of products: 1 created» (the deleted
// group's option came back with it, counted once), and its page notes that the service
// category came back without the service moved
// since and the service without the terminated professional, and why; and `a` has the same card live
// again in its group, the second one again in that group with its tag and its value, the same product live again in
// its category back under a new id with its price in its price list, asking for its group and offered in its menu,
// made again with its course under new ids, the
// category asking for its own group, made again with its option, the kept product in it
// again, the same appointment (its number, its history
// ending in «restored») live again, and the service category and the service live again under new ids, the service in
// that category and performed by that professional again; in its Agenda, the appointment's «History» ends in
// «Restored» (APPOINTMENT-F10).
// The stack's worker serves databases only (no moves' thread), so the spec plays its passes, as the specs play the
// relay, in one `manage.py shell` opened before the tests (`manage-shell.ts`). What the business has and loses goes
// through its apps' API with the owner's session, as in the other specs, but for what no person does.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { nameOf } from './business';
import { WORKER_START_TIMEOUT_MS } from './global-setup';
import { capture, OWNER, psql } from './helpers';
import { GENERIC } from './inventory-helpers';
import { openShell, type Shell } from './manage-shell';
import { ownerPage, post, rowAction } from './service-helpers';
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

/** POST `path` of `a`'s API with the owner's session in `business`; the id of what it made, if it made one. */
async function inA(business: BrowserContext, path: string, body: Record<string, unknown>, status = 200): Promise<string> {
  return (await post<{ id?: string }>(business, path, body, status)).id ?? '';
}

/** What `path` of `a`'s API makes (201) with `body`; its id. */
const made = (business: BrowserContext, path: string, body: Record<string, unknown>): Promise<string> =>
  inA(business, path, body, 201);

/** What the platform runs in `a` as the system, each operation with its input: the worker's relay (the stack's worker
 *  relays nothing) and what no person does. */
async function bySystem(calls: [string, Record<string, unknown>][]): Promise<void> {
  await shell.run(
    [
      'import json',
      'from base.registry import hub_by_slug',
      'from base.tenancy.context import use_hub',
      'from live.context import OperationContext, Scope',
      'from live.operations import get',
      'ctx = OperationContext(scope=Scope("host", "a"), actor="system", permissions=frozenset({"*"}), language="en")',
      'with use_hub(hub_by_slug("a")):',
      `    for name, data in json.loads(${JSON.stringify(JSON.stringify(calls))}):`,
      '        op = get(name)',
      '        op(ctx, op.input(**data))',
    ].join('\n'),
  );
}

/** A product of `a` made by Inventory's create, in `category`; its id. */
function aProduct(business: BrowserContext, name: string, sku: string, category: string): Promise<string> {
  return made(business, '/inventory/products', { name, sku, price: 250, tax_category_key: GENERIC, category_ids: [category] });
}

/** A service of `a` made by Services' create, in `category`; its id. */
function aService(business: BrowserContext, name: string, category: string): Promise<string> {
  const service = { name, price: 2500, duration_minutes: 45, category_id: category, tax_category_key: 'service.generic' };
  return made(business, '/service/services', service);
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
async function anAppointment(business: BrowserContext, label: string): Promise<string> {
  const customer = await made(business, '/customer/customers', { name: `Booked ${label} ${RUN}`, email: `booked-${label}-${RUN}@example.com` });
  const staff = await made(business, '/staff/members', { first_name: 'Booked', last_name: `${label} ${RUN}` });
  const service = await made(business, '/service/services', {
    name: `Cut ${label} ${RUN}`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  return made(business, '/appointment/appointments', {
    customer_id: customer,
    staff_id: staff,
    services: [{ service_id: service }],
    start: aMondayAt('10:00'),
  });
}

/** Control's side, by `step`: `setup` makes the staff member and the temporary cluster once and opens the staff
 *  member's session (its key), `make` runs the worker's pass of the separate copies (the latest copy of `a`, made;
 *  its copy goes through a dumps bucket of its own, on a tests' S3 server emptied first: its state lives in the
 *  shell), `recover` runs its pass of the recoveries, and `clean` drops the copies of `a` with their rows and the
 *  temporary cluster. Its last line. */
async function control(step: 'setup' | 'make' | 'recover' | 'clean'): Promise<string> {
  const out = await shell.run(
    [
      'from django.contrib.auth import get_user_model',
      'from django.db import connections',
      'from base.tenancy import move, recovery, restore',
      'from control.models.copies import RestoredCopy',
      'from control.models.hubs import Cluster, Hub',
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
      '    import os, urllib.request',
      '    from unittest import mock',
      '    from moto.server import ThreadedMotoServer',
      '    from base.tenancy.tests.s3 import FAKE_CREDENTIALS, REGION, client',
      '    s3 = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)',
      '    s3.start()',
      '    try:',
      '        endpoint = "http://%s:%d" % s3.get_host_and_port()',
      '        urllib.request.urlopen(urllib.request.Request(endpoint + "/moto-api/reset", method="POST"))',
      '        dumps = dict(FAKE_CREDENTIALS, AWS_REGION=REGION, HUB_DUMPS_BUCKET="e2e-copies", HUB_DUMPS_ENDPOINT_URL=endpoint)',
      '        with mock.patch.dict(os.environ, dumps):',
      '            os.environ.pop("AWS_PROFILE", None)',
      '            client(endpoint).create_bucket(Bucket="e2e-copies", CreateBucketConfiguration={"LocationConstraint": REGION})',
      '            restore.run_aside_due(source=lambda copied: copied.db_name)',
      '    finally:',
      '        s3.stop()',
      '    made = RestoredCopy.objects.filter(hub=hub).order_by("-asked_at").first()',
      '    assert made.status == "made", made.last_error',
      '    print(made.pk)',
      'elif step == "recover":',
      '    print(recovery.run_due())',
      'else:',
      '    for copy in RestoredCopy.objects.filter(hub=hub, db_name__contains="_copy_"):',
      '        move.databases._drop_copy(copy.db_name, copy.cluster)',
      '        copy.delete()',
      '    Cluster.objects.filter(pk=temporary.pk).delete()',
      '    print("clean")',
    ]
      .join('\n')
      .replace('TEMPORARY', JSON.stringify(TEMPORARY)),
  );
  return out.split('\n').at(-1) ?? '';
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

/** The spec's `manage.py shell` on control, open from before the first test to after the last, and the staff member's
 *  session, opened once for every size. */
let shell: Shell;
let staffSession: string;

test.beforeAll(async () => {
  // Django's start, before the tests' time and bounded as the run's worker's is.
  test.setTimeout(WORKER_START_TIMEOUT_MS);
  shell = await openShell();
  staffSession = await control('setup');
});

test.afterAll(async () => {
  // A shell that never opened made nothing to clean.
  if (!shell) return;
  await control('clean');
  await shell.close();
});

for (const { label, viewport } of SIZES) {
  test(`${KEY}: at ${label}, the staff choose a separate copy and the customer, the product, the service and the appointment the business lost come back`, async ({ browser }) => {
    test.slow();
    const { context: business, page: landing } = await ownerPage(browser, '/appointment/agenda', viewport);
    // Only its session is needed: the business runs one transaction at a time, and an open page's live queries would
    // take it from the requests below.
    await landing.close();
    const name = `Recovered ${label} ${RUN}`;
    const email = `recovered-${label}-${RUN}@example.com`;
    const card = await made(business, '/customer/customers', { name, email });
    // What hangs from the cards: a group both are in, and a tag and a custom field's value of the second.
    const group = await made(business, '/customer/groups', { name: `VIP ${label} ${RUN}` });
    const tagName = `Regular ${label} ${RUN}`;
    const tag = await made(business, '/customer/tags', { name: tagName, color: 'success' });
    const field = await made(business, '/customer/fields', { name: `Size ${label} ${RUN}` });
    const goneEmail = `gone-${label}-${RUN}@example.com`;
    const goneCard = await made(business, '/customer/customers', { name: `Gone ${label} ${RUN}`, email: goneEmail });
    await inA(business, '/customer/customers/set_groups', { id: card, group_ids: [group] });
    await inA(business, '/customer/customers/set_groups', { id: goneCard, group_ids: [group] });
    await inA(business, '/customer/customers/set_tags', { id: goneCard, tag_ids: [tag] });
    await inA(business, '/customer/customers/update', { id: goneCard, field_values: [{ field_id: field, value: 'M' }] });
    const sku = `REC-${label}-${RUN}`;
    const shelf = await made(business, '/inventory/categories', { name, color: '#33aa66' });
    const product = await aProduct(business, name, sku, shelf);
    const priceList = await made(business, '/pricing/price_lists', { code: `REC-${label}-${RUN}`, name });
    await made(business, '/pricing/price_items', { price_list_id: priceList, product_id: product, price: 900 });
    const sauces = await made(business, '/modifier/groups', { name: `Sauces ${label} ${RUN}` });
    await made(business, '/modifier/links/attach', { group_id: sauces, product_id: product });
    // Kept by the business, which takes this option away from it after the copy.
    const alioli = await made(business, '/modifier/options', {
      group_id: sauces, name: 'Alioli', price_delta: 50, is_default: true, sort_order: 1,
    });
    const extras = await made(business, '/modifier/groups', { name: `Extras ${label} ${RUN}` });
    await made(business, '/modifier/options', { group_id: extras, name: 'Cheese', price_delta: 100 });
    await made(business, '/modifier/links/attach', { group_id: extras, category_id: shelf });
    const menu = await made(business, '/combo/combos', { name: `Menu ${label} ${RUN}`, price: 1350, tax_category_key: GENERIC });
    const mains = await made(business, '/combo/groups', { combo_id: menu, name: 'Mains' });
    await made(business, '/combo/options', { group_id: mains, product_id: product, price_delta: 150 });
    // Kept live by the business: deleting the category takes it out of it.
    const kept = await aProduct(business, `Kept ${label} ${RUN}`, `KEPT-${label}-${RUN}`, shelf);
    const category = await made(business, '/service/categories', { name, color: '#cc0066' });
    const service = await aService(business, name, category);
    // Kept by the business: deleting the category leaves them without one; the second it moves to another one.
    const keptService = await aService(business, `Kept ${label} ${RUN}`, category);
    const movedService = await aService(business, `Moved ${label} ${RUN}`, category);
    // And a subcategory of it, which deleting the category moves up to the root.
    const keptSubcategory = await made(business, '/service/categories', { name: `Under ${label} ${RUN}`, parent_id: category });
    const professional = await made(business, '/staff/members', { first_name: 'Recovered', last_name: `${label} ${RUN}` });
    await inA(business, '/service/assignments/assign', { service_id: service, member_id: professional, custom_duration: 50, custom_price: 2800 });
    // And one who performed it too and leaves the business before it comes back.
    const leaving = await made(business, '/staff/members', { first_name: 'Leaving', last_name: `${label} ${RUN}` });
    await inA(business, '/service/assignments/assign', { service_id: service, member_id: leaving });
    const appointment = await anAppointment(business, label);
    const number = psql(`select number from appointment_appointment where id = '${appointment}'`);
    const hubId = psql("select id from base_hub where slug = 'a'");

    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await context.addCookies([{ name: 'sessionid', value: staffSession, domain: 'hubs.localhost', path: '/' }]);

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
    const copy = await control('make');
    // Lost since: the card, the product, the product's category and the service's category deleted in the business.
    await inA(business, '/customer/customers/delete', { id: card });
    await inA(business, '/inventory/products/delete', { id: product });
    await inA(business, '/inventory/categories/delete', { id: shelf });
    await bySystem([
      ['pricing.catalog.forget_product', { id: product }],
      ['modifier.link.drop_product', { id: product }],
      ['combo.option.drop_product', { id: product }],
      ['modifier.link.drop_category', { id: shelf }],
    ]);
    // And the option taken away from the group it keeps.
    await inA(business, '/modifier/options/delete', { id: alioli });
    // And the menu it was offered in, withdrawn with its course.
    await inA(business, '/combo/combos/delete', { id: menu });
    // And the group the category asked for, deleted by Modifiers with its option.
    await inA(business, '/modifier/groups/delete', { id: extras });
    await inA(business, '/service/categories/delete', { id: category });
    const elsewhere = await made(business, '/service/categories', { name: `Elsewhere ${label} ${RUN}` });
    await inA(business, '/service/services/update', { id: movedService, category_id: elsewhere });
    // And the appointment, deleted by the platform: its history then holds a line of a person and lines of no one.
    await bySystem([['appointment.appointment.delete', { id: appointment }]]);
    await inA(business, '/staff/members/terminate', { id: leaving });
    expect(psql(`select count(*) from customer_customer where email = '${email}' and deleted_at is null`)).toBe('0');
    expect(psql(`select count(*) from inventory_product where sku = '${sku}' and not is_deleted`)).toBe('0');
    expect(psql(`select count(*) from pricing_priceitem where product_id = '${product}'`)).toBe('0');
    expect(psql(`select count(*) from modifier_modifierlink where product_id = '${product}'`)).toBe('0');
    expect(psql(`select count(*) from modifier_modifierlink where category_id = '${shelf}'`)).toBe('0');
    expect(psql(`select count(*) from modifier_modifieroption where group_id = '${extras}'`)).toBe('0');
    expect(psql(`select count(*) from modifier_modifieroption where group_id = '${sauces}'`)).toBe('0');
    expect(psql(`select count(*) from combo_choiceoption where product_id = '${product}'`)).toBe('0');
    expect(psql(`select count(*) from combo_choicegroup where combo_id = '${menu}'`)).toBe('0');
    expect(psql(`select count(*) from inventory_productcategory where product_id = '${kept}'`)).toBe('0');
    // The second card gone from the business altogether, with what hung from it (a lost database, or the Hub admin's
    // «Delete»), and the tag deleted by Customers' own operation.
    for (const table of ['customer_customer_groups', 'customer_customer_tags', 'customer_customfieldvalue']) {
      psql(`delete from ${table} where customer_id = '${goneCard}'`);
    }
    psql(`delete from customer_customer where id = '${goneCard}'`);
    await inA(business, '/customer/tags/delete', { id: tag });
    await business.close();
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
    await expect(page.locator('input[name="apps"][value="pricing"]')).toBeChecked();
    await expect(page.locator('input[name="apps"][value="modifier"]')).toBeChecked();
    await expect(page.locator('input[name="apps"][value="combo"]')).toBeChecked();
    await expect(page.getByText('nothing is ever copied', { exact: false })).toBeVisible();
    await expect(page.getByText('comes back as it was, with its history', { exact: false })).toBeVisible();
    // The one thing it touches of what the business has.
    await expect(page.getByText('a category that comes back takes back what it had inside', { exact: false })).toBeVisible();
    await capture(page, `${KEY}-${label}-2-confirm`, { fullPage: true });
    await page.locator('input[type="submit"][value="Recover"]').click();

    // What else answers (another app's recovery) may sit among them, in the apps' order.
    await expect(page.locator('.messagelist .success')).toContainText(
      /1 separate copy will give back (.+, )?Customers, (.+, )?Products, (.+, )?Services(, .+)? into its business within a few minutes/,
    );
    await capture(page, `${KEY}-${label}-3-asked`);

    // The worker's pass, then Recoveries says what came back.
    expect(await control('recover')).toBe('1');
    await page.goto(RECOVERIES);
    const recovered = page.locator('#result_list tbody tr').first();
    await expect(recovered).toContainText('Done');
    await expect(recovered).toContainText('Customers: 1 restored, 1 created');
    await expect(recovered).toContainText(
      'Product categories: 1 created; Products: 1 restored; Product links to categories: 1 created',
    );
    // The service category came back without the service moved since, and the service without the professional Staff
    // terminated: each counted, and said on its page.
    await expect(recovered).toContainText(
      'Service categories: 1 created, 1 with notes; Services: 1 created, 1 with notes; ' +
        'Service links to categories: 1 created; Subcategory links to categories: 1 created',
    );
    await expect(recovered).toContainText('Appointments: 1 restored; Repeating appointments: 0 created');
    await expect(recovered).toContainText('Price list prices: 1 created');
    await expect(recovered).toContainText('Menus: 1 created; Menu courses: 1 created; Menu choices of products: 1 created');
    await expect(recovered).toContainText(
      'Modifier groups: 1 created; Modifier options: 1 created; Modifier groups of categories: 1 created; ' +
        'Modifier groups of products: 1 created',
    );
    await capture(page, `${KEY}-${label}-4-recoveries`, { fullPage: true });
    await recovered.locator('a').first().click();
    await expect(page.locator('.field-what .readonly')).toHaveText(/^(.+, )?Customers, (.+, )?Products, (.+, )?Services(, .+)?$/);
    await expect(page.locator('.field-notes .readonly li')).toHaveText([
      `${category}: service.service_moved: came back without the service ${movedService}: moved to another category since`,
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
    // With its price in its price list again, put by Price Lists' add after Inventory brought the product back.
    expect(psql(`select price from pricing_priceitem where product_id = '${product}' and price_list_id = '${priceList}'`)).toBe('900');
    // And asking for its modifier group again, linked by Modifiers' attach after Inventory brought the product back.
    expect(psql(`select group_id from modifier_modifierlink where product_id = '${product}'`)).toBe(sauces);
    // And that group, which the business kept, offers again the option it took away, added by Modifiers as it was: its
    // supplement, chosen by default (no other one is) and its place.
    const optionAgain = `select name || '|' || price_delta || '|' || is_default || '|' || sort_order from modifier_modifieroption where group_id = '${sauces}'`;
    expect(psql(optionAgain)).toBe('Alioli|50|true|1');
    // And offered again as a main of its menu, with its supplement, by Menus' create after Inventory brought it back:
    // in the course Menus made again for the copy's, in the menu it made again for the one the business withdrew.
    const offeredAgain =
      "select g.name || '|' || o.price_delta || '|' || g.stands_for || '|' || c.stands_for from combo_choiceoption o " +
      'join combo_choicegroup g on g.id = o.group_id join combo_combo c on c.id = g.combo_id ' +
      `where o.product_id = '${product}'`;
    expect(psql(offeredAgain)).toBe(`Mains|150|${mains}|${menu}`);
    // In its category, back before it: a new one, made by Categories' create, with its colour; the deleted one stays
    // deleted.
    const shelfBack = psql(`select id from inventory_category where name = '${name}' and not is_deleted`);
    expect(shelfBack).not.toBe(shelf);
    expect(psql(`select color from inventory_category where id = '${shelfBack}'`)).toBe('#33aa66');
    expect(psql(`select category_id from inventory_productcategory where product_id = '${product}'`)).toBe(shelfBack);
    // Asking for its modifier group again, made again by Modifiers with its option (a new one: the deleted one is gone)
    // and linked by Modifiers' attach to the category brought back.
    const extrasBack = psql(`select id from modifier_modifiergroup where name = 'Extras ${label} ${RUN}'`);
    expect(extrasBack).not.toBe(extras);
    expect(psql(`select name || '|' || price_delta from modifier_modifieroption where group_id = '${extrasBack}'`)).toBe('Cheese|100');
    expect(psql(`select group_id from modifier_modifierlink where category_id = '${shelfBack}'`)).toBe(extrasBack);
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
    // The service the business kept, the same one, back in it; the one it moved since stays where it put it.
    expect(psql(`select category_id from service_service where id = '${keptService}'`)).toBe(back);
    expect(psql(`select category_id from service_service where id = '${movedService}'`)).toBe(elsewhere);
    // And the subcategory it kept at the root, the same one, hanging from it again.
    expect(psql(`select parent_id from service_category where id = '${keptSubcategory}'`)).toBe(back);
    // And performed again by the same professional, with her own minutes and price, by Services' assign.
    const performer = `select member_id, custom_duration, custom_price, is_active from service_assignment where service_id = (select id from service_service where name = '${name}')`;
    expect(psql(performer)).toBe(`${professional}|50|2800|t`);
    // And the same appointment on the agenda again, by Appointments' restore: its number, its history ending in
    // «restored», and no new one booked for its card.
    expect(psql(`select number, deleted_at is null from appointment_appointment where id = '${appointment}'`)).toBe(`${number}|t`);
    expect(psql(`select action from appointment_history where appointment_id = '${appointment}' order by at desc, id desc limit 1`)).toBe('restored');
    expect(psql(`select count(*) from appointment_appointment where customer_name = 'Booked ${label} ${RUN}'`)).toBe('1');
    await context.close();

    // In the business's Agenda, its «History» keeps its lines and ends in «Restored» (APPOINTMENT-F10). The owner booked
    // it, and that line names the owner; the platform deleted it and the recovery brought it back, and those say so.
    const agenda = await ownerPage(browser, `/appointment/agenda?date=${aMondayAt('10:00').slice(0, 10)}`, viewport);
    await rowAction(agenda.page, 'appointment-list', appointment, 'history');
    const history = agenda.page.locator('ion-modal[data-testid=appointment-history-modal]');
    const owner = nameOf(OWNER);
    await expect(history.locator('[data-testid=appointment-history-entry]')).toHaveText([
      new RegExp(`^Booked.* · ${owner}$`),
      /^Deleted.* · Done by the platform$/,
      /^Restored.* · Done by the platform$/,
    ]);
    await capture(agenda.page, `${KEY}-${label}-6-history`);
    await agenda.context.close();
  });
}
