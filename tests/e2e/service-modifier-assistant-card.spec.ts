// hub#676 and hub#672: since hub#416 the assistant's card left out every id its schema does not mark, so «anula ese bono»
// or «borra esa opción» said no voucher and no option. Now each record is named as the Services and Modifiers screens
// show it, read as the person, in their language, never by its id. End to end with the stack's SaaS gateway and the
// e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it (README of this
// folder, «El asistente»). Cancelled, nothing changes. What this file creates carries its own prefix (E2ESMC) and goes
// away; the apps it turns on are turned off again.
// flow: SERVICE-F17 SERVICE-F32 MODIFIER-F04 MODIFIER-F05 BASE-F97
import { execSync } from 'node:child_process';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, capture, compactBar, login, psql, REPO_DIR, shown, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { createProduct, post, stamp } from './pricing-helpers';
import { STACK } from './stack';

/** An id as a schema's `format: uuid` takes it: never on a card. */
const AN_ID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const VIEWPORTS = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);
/** The apps the records need: a business is born with every app off. */
const NEEDED = ['inventory', 'tax', 'customer', 'staff', 'service', 'modifier'];
const PREFIX = 'E2ESMC';
const RUN = stamp();

/** What each screen calls the record, by the language of the card. */
const TITLES = {
  es: { grant: 'Bono vendido', assignment: 'Profesional del servicio', option: 'Opción', link: 'Se aplica a' },
  en: { grant: 'Voucher sold', assignment: 'Professional of a service', option: 'Option', link: 'Applies to' },
};
type Language = keyof typeof TITLES;
/** The word the card calls a record by when nothing titles it, in each language. */
const GENERIC = { es: 'Registro', en: 'Record' };

let provider: Provider;
/** The apps this file turned on, in that order (`turnOnMissing`): its `afterAll` turns off these and nothing else. */
const turnedOn: string[] = [];

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** Deletes what this file created (names and SKUs `E2ESMC…`). */
function cleanUp(): void {
  const named = `like '${PREFIX}%'`;
  const packages = `select id from service_package where name ${named}`;
  const services = `select id from service_service where name ${named}`;
  const groups = `select id from modifier_modifiergroup where name ${named}`;
  const products = `select id from inventory_product where sku ${named}`;
  psql(
    [
      `delete from service_grant where package_id in (${packages})`,
      `delete from service_packageitem where package_id in (${packages})`,
      `delete from service_package where name ${named}`,
      `delete from service_assignment where service_id in (${services})`,
      `delete from service_service where name ${named}`,
      `delete from staff_member where first_name ${named}`,
      `delete from customer_customer where name ${named}`,
      `delete from modifier_modifierlink where group_id in (${groups})`,
      `delete from modifier_modifieroption where group_id in (${groups})`,
      `delete from modifier_modifiergroup where name ${named}`,
      `delete from inventory_stockmovement where product_id in (${products})`,
      `delete from inventory_productcategory where product_id in (${products})`,
      `delete from inventory_product where sku ${named}`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOnMissing(context, A, NEEDED, turnedOn);
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test.beforeEach(() => {
  // The month's assistant messages of the business `a` back to none: a run never spends the plan's allowance.
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
  cleanUp();
});

test.afterAll(async ({ browser }) => {
  cleanUp();
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
  await provider?.close();
});

// ── The panel and its card (as base-assistant.spec.ts drives them) ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function openPanel(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/** Writes `text` and sends it; resolves once its answer has started (its card is up before the turn ends). */
async function ask(page: Page, text: string): Promise<void> {
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
}

type SentCard = { fields: { name: string; label: string; value: unknown }[] };

/** The card of the confirm frame of a turn's answer (`text/event-stream`: one `data: <JSON>` per frame), if any. */
function confirmedCard(stream: string): SentCard | undefined {
  const frames = stream
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => JSON.parse(line.slice(5)) as { type: string; card?: SentCard });
  return frames.find((frame) => frame.type === 'confirm')?.card;
}

/** The card the server sends for the person to confirm, as it arrives: the answer of the turn that carries it. */
async function sentCard(page: Page): Promise<SentCard> {
  const answer = await page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
  );
  return confirmedCard(await answer.text())!;
}

/** Asks for the write `tool` and returns the datum `id` of the card that comes up, never saying an id on the way. */
async function cardOf(page: Page, tool: string, data: Record<string, unknown>): Promise<{ label: string; value: unknown }> {
  const sent = sentCard(page);
  await ask(page, `E2E-ASK ${tool} ${JSON.stringify(data)}`);
  await expect(card(page)).toBeVisible();
  const fields = (await sent).fields;
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).not.toContainText(AN_ID);
  const field = fields.find((one) => one.name === 'id');
  expect(field, `the card of ${tool} names no record: ${JSON.stringify(fields)}`).toBeDefined();
  return field!;
}

async function cancel(page: Page): Promise<void> {
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
}

async function ownerIn(browser: Browser, language: Language): Promise<[BrowserContext, Page]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  return [context, page];
}

/** A haircut Ana performs and a voucher of it sold to Lucía, through each app's API. */
async function aSalon(context: BrowserContext, tag: string) {
  const service = await post<{ id: string; name: string }>(context, '/service/services', {
    name: `${PREFIX} Corte ${tag}`,
    price: 2000,
    duration_minutes: 30,
    tax_category_key: 'service.generic',
  });
  const member = await post<{ id: string; full_name: string }>(context, '/staff/members', { first_name: `${PREFIX} Ana ${tag}`, last_name: 'López' });
  const assignment = await post<{ id: string }>(context, '/service/assignments/assign', { service_id: service.id, member_id: member.id }, 200);
  const customer = await post<{ id: string; name: string }>(context, '/customer/customers', {
    name: `${PREFIX} Lucía ${tag}`,
    phone: `6${String(Date.now()).slice(-8)}`,
  });
  const voucher = await post<{ id: string; name: string }>(context, '/service/packages', {
    name: `${PREFIX} Bono ${tag}`,
    items: [{ service_id: service.id, sessions: 5 }],
  });
  const grant = await post<{ id: string }>(context, '/service/grants', { package_id: voucher.id, customer_id: customer.id });
  return { service, member, assignment, customer, voucher, grant };
}

/** A group of sauces with an option, hung from a product, through each app's API. */
async function aGroup(context: BrowserContext, tag: string) {
  const group = await post<{ id: string; name: string }>(context, '/modifier/groups', { name: `${PREFIX} Salsas ${tag}` });
  const option = await post<{ id: string; name: string }>(context, '/modifier/options', { group_id: group.id, name: `${PREFIX} Alioli ${tag}` });
  const name = `${PREFIX} Hamburguesa ${tag}`;
  const product = await createProduct(context, name, `${PREFIX}-${tag}`, 900);
  const link = await post<{ id: string }>(context, '/modifier/links/attach', { group_id: group.id, product_id: product.id });
  return { group, option, product: { ...product, name }, link };
}

for (const language of ['es', 'en'] as const) {
  const titles = TITLES[language];

  test(`service-assistant-card — in ${language}, voiding a voucher and removing a professional name which, never by their id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const salon = await aSalon(context, `${RUN}${language}`);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Anula ese bono», a dangerous write: the voucher by its package, its owner and the day it was sold.
    const voided = await cardOf(page, 'service__grant__void', { id: salon.grant.id, reason: 'Sold by mistake' });
    expect(voided.label).toBe(titles.grant);
    const said = String(voided.value);
    expect(said.startsWith(`${salon.voucher.name} · ${salon.customer.name} · `), said).toBe(true);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${titles.grant}: ${said}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-676-service-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Quítale ese servicio a Ana»: who does what, by the service and the professional.
    const removed = await cardOf(page, 'service__assignment__remove', { id: salon.assignment.id });
    expect(removed.label).toBe(titles.assignment);
    expect(removed.value).toBe(`${salon.service.name} · ${salon.member.full_name}`);
    await expect(card(page)).toContainText(String(removed.value));
    await cancel(page);

    // Cancelled, nothing changed, and the reads that name them answer by the same routes as any other client.
    const grant = await api<{ status: string; label: string }>(context, A, 'GET', `/service/grants/detail?id=${salon.grant.id}`);
    expect(grant.status, JSON.stringify(grant.data)).toBe(200);
    expect(grant.data.status).toBe('active');
    const assignment = await api<{ is_active: boolean; label: string }>(context, A, 'GET', `/service/assignments/detail?id=${salon.assignment.id}`);
    expect(assignment.status, JSON.stringify(assignment.data)).toBe(200);
    expect(assignment.data.is_active).toBe(true);
    await context.close();
  });

  test(`modifier-assistant-card — in ${language}, deleting an option and detaching a group name which, never by their id`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    const sauces = await aGroup(context, `${RUN}${language}`);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);

    // «Borra el alioli», a dangerous write: the option by its name and its group, as two groups may have one with that name.
    const deleted = await cardOf(page, 'modifier__option__delete', { id: sauces.option.id });
    expect(deleted.label).toBe(titles.option);
    expect(deleted.value).toBe(`${sauces.option.name} (${sauces.group.name})`);
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(`${titles.option}: ${String(deleted.value)}`);
      await expect(card(page)).not.toContainText(GENERIC[language]);
      await expect(card(page)).not.toContainText(AN_ID);
      await untilStill(page);
      await capture(page, `hub-672-modifier-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // «Quita las salsas de la hamburguesa»: the link by its group and what it hangs from.
    const detached = await cardOf(page, 'modifier__link__detach', { id: sauces.link.id });
    expect(detached.label).toBe(titles.link);
    expect(detached.value).toBe(`${sauces.group.name} · ${sauces.product.name}`);
    await expect(card(page)).toContainText(String(detached.value));
    await cancel(page);

    // Cancelled, nothing changed: the option and the link are still there.
    const option = await api<{ id: string }>(context, A, 'GET', `/modifier/options/detail?id=${sauces.option.id}`);
    expect(option.status, JSON.stringify(option.data)).toBe(200);
    const link = await api<{ id: string }>(context, A, 'GET', `/modifier/links/detail?id=${sauces.link.id}`);
    expect(link.status, JSON.stringify(link.data)).toBe(200);
    await context.close();
  });
}
