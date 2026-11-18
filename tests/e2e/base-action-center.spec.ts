// flow: BASE-F01 BASE-F10 INVOICE-F21 APPOINTMENT-F03
// The hub's action center (base's WORKBOOK, «La campana» and «El aviso «Todavía no puedes facturar»»), as the owner of
// hub `a` meets it in Spanish at 390, 834 and 1440, in light and dark: the bell's pill with its number and the gravest
// notice's colour; a new notice comes as a card and settles in the bell; the panel opens with «Todavía no puedes
// facturar» on top and the counters in rows, and closes with Esc or a tap outside, giving the focus back to the bell;
// with the assistant open the card comes in to its left and the panel opens over it; with the till's charge sheet open
// no card comes, the bell only counts; and once the business details are saved, «Todavía no puedes facturar» goes.
// The bar keeps the title centred: on a phone its end holds «⋮» and the bell, and «⋮» lists «Mis apps» and «Asistente»,
// each opening its own; from a tablet «Mis apps», the sparkles and the bell are all on it.
// The new notice is the demo's «open demo items» counter, raised and dropped through Demo's operations. A booking a
// customer made, waiting for confirmation two days ahead, is the notice whose words the server gives: «N citas por
// confirmar», its sentence, «Confirmar las citas» and its deadline, the booking's start, on the bell's ring. Hub `a`'s
// issuer is parked for the run and put back as it was after it, and Citas's «confirm automatically» too.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  actionBell,
  actionPanel,
  arrivalCard,
  bellRingLeft,
  bellSays,
  bellTotal,
  closeActionCenter,
  expectTheServersWords,
  featuredNotice,
  featureNotice,
  noticeButton,
  noticeIn,
  openActionCenter,
  serverCounter,
} from './action-center';
import { openForACut, salonCleanUp } from './appointment-helpers';
import { cardDeletes } from './customer-helpers';
import { A, api, capture, clearItems, compactBar, horizontalOverflow, login, psql, shown, uniqueName } from './helpers';
import { spanishContext, spanishHome } from './home-helpers';
import { cleanInventory, type Product, VIEWPORTS } from './inventory-helpers';
import { type IssuerOut, issuerNow, parkIssuer, unparkIssuer } from './invoice-helpers';
import { checkWithDish, cleanSales, dishForTheTill } from './sale-helpers';
import { post } from './service-helpers';
import { expectTitleCentred, openApps, openAssistant, topbar, topbarMore, topbarMoreMenu } from './topbar';

const KEY = 'BASE-ACTION-CENTER';
/** Hub `a`'s issuer, parked while the run needs a business that cannot issue invoices yet. */
const PARKED = 'e2e_base_action_center_issuer';
const SIZES = VIEWPORTS;
const SCHEMES = ['light', 'dark'] as const;
const BLOCKING = 'Todavía no puedes facturar';
const DEMO_NOTICE = '1 elemento de demo abierto';
/** What the bookings, the professional and the open day of the run are named. */
const TAG = 'E2E Center';
/** Two days ahead: inside the last week before the booking, when the bell's ring counts down to it. */
const BOOKING_DAY = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
/** What the issuer is saved with when the hub had none before the run. */
const ISSUER = { legal_name: 'e2e Bar Centro SL', tax_id: 'B12345674', address: 'Calle Mayor 1', postal_code: '28001', city: 'Madrid', province: 'Madrid', country: 'ES' };

let original: IssuerOut;
let dish: Product;
/** Citas's «confirm automatically» before the run, put back after it. */
let autoConfirm: boolean | undefined;
let salon: { customer: { id: string }; service: { id: string }; member: { id: string } };

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/');
  original = await issuerNow(context);
  await context.close();
  parkIssuer(PARKED);
  dish = await dishForTheTill(browser, 'CENTER', Date.now().toString(36).toUpperCase());
  await asOwner(browser, async (context) => {
    cleanSalon();
    const settings = await api<{ auto_confirm_online: boolean }>(context, A, 'GET', '/appointment/settings');
    expect(settings.status).toBe(200);
    autoConfirm = settings.data.auto_confirm_online;
    // «I review them first»: a booking the customer makes waits for the business.
    await post(context, '/appointment/settings', { auto_confirm_online: false }, 200);
    const customer = await post<{ id: string }>(context, '/customer/customers', { name: `${TAG} Lucía`, phone: `6${String(Date.now()).slice(-8)}` });
    salon = { customer, ...(await openForACut(context, TAG, BOOKING_DAY)) };
  });
});

test.afterAll(async ({ browser }) => {
  try {
    cleanSales();
    cleanInventory();
    const before = autoConfirm;
    if (before !== undefined) await asOwner(browser, (context) => post(context, '/appointment/settings', { auto_confirm_online: before }, 200));
  } finally {
    cleanSalon();
    unparkIssuer(PARKED);
  }
});

async function asOwner(browser: Browser, run: (context: BrowserContext) => Promise<unknown>): Promise<void> {
  const context = await browser.newContext({ baseURL: A });
  try {
    await login(await context.newPage(), A, '/');
    await run(context);
  } finally {
    await context.close();
  }
}

/** The bookings, the professional, the service, the open day and the customer of the run. */
function cleanSalon(): void {
  psql([...salonCleanUp(TAG), ...cardDeletes(`select id from customer_customer where name like '${TAG}%'`)].join('; '));
}

/** The owner of `a` on the Home in Spanish, in the colour scheme `scheme`. */
async function spanishOwner(browser: Browser, size: (typeof SIZES)[number], scheme: (typeof SCHEMES)[number]) {
  const context = await spanishContext(browser, { width: size.width, height: size.height });
  const page = await context.newPage();
  await page.emulateMedia({ colorScheme: scheme });
  await spanishHome(page);
  return { context, page };
}

/** No receipt left waiting by an earlier run: «Nothing is printing …» moves with the clock, with no event, so the
 *  bell and a fresh read of the server could disagree while it moves. */
function noPrintsWaiting(): void {
  psql("delete from printing_printjob where status = 'pending'");
}

/** A new notice: the demo's counter of open items, from none to one. */
async function raiseDemoNotice(context: BrowserContext): Promise<void> {
  const created = await api(context, A, 'POST', '/demo/items', { name: uniqueName('Action center') });
  expect(created.status).toBe(201);
}

/** Waits until no card is on screen: one that another notice of the business brought settles in the bell first. */
async function noCardOnScreen(page: Page): Promise<void> {
  await expect(arrivalCard(page)).toHaveCount(0, { timeout: 15_000 });
}

/** The bell says what the server counts now. */
async function bellSaysTheServer(page: Page, context: BrowserContext): Promise<number> {
  const total = await bellTotal(context);
  await bellSays(page, total);
  return total;
}

async function captured(page: Page, state: string, scheme: string, label: string): Promise<void> {
  const overflow = await horizontalOverflow(page);
  expect(overflow, `no sideways scroll: ${state} at ${label}`).toBeLessThanOrEqual(0);
  await capture(page, `${KEY}-${state}-${scheme}-${label}`);
}

/** The bell holds the focus once the panel has gone (Ionic's button keeps its focusable part in its shadow root). */
async function expectFocusOnTheBell(page: Page): Promise<void> {
  await expect.poll(() => page.evaluate(() => document.activeElement?.closest('[data-testid=action-bell]') !== null)).toBe(true);
}

/** A new notice comes as a card under the bar, says its words, and settles in the bell, which then counts it. */
async function expectArrival(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  await noCardOnScreen(page);
  await raiseDemoNotice(context);
  const card = arrivalCard(page);
  await expect(card).toBeVisible();
  await expect(card).toContainText(DEMO_NOTICE);
  await card.hover();
  await shotOf('arrival');
  await page.mouse.move(1, 1);
  await expect(card).toBeHidden({ timeout: 15_000 });
  await bellSaysTheServer(page, context);
}

async function expectThePanel(page: Page, size: (typeof SIZES)[number], shotOf: (state: string) => Promise<void>): Promise<void> {
  const panel = await openActionCenter(page);
  const featured = featuredNotice(panel);
  await expect(featured.locator('h3')).toHaveText(BLOCKING);
  await expect(featured).toContainText('No se podrá emitir ningún tique ni factura hasta que configures esto:');
  await expect(featured).not.toContainText(/\btickets?\b/i);
  await expect(noticeButton(featured, 'Configurar los datos del negocio')).toBeVisible();
  await expect(panel.locator('[data-testid=action-row]').filter({ hasText: DEMO_NOTICE })).toBeVisible();
  await shotOf('panel');
  await closeActionCenter(page);
  await expectFocusOnTheBell(page);
  await openActionCenter(page);
  if (compactBar(page)) {
    await panel.locator('[data-testid=action-panel-close]').click();
  } else {
    // A tap outside: on the screen's left, which the panel (400 px from the right) leaves uncovered.
    await page.mouse.click(10, Math.round(size.height / 2));
  }
  await expect(actionPanel(page)).toBeHidden();
  await expectFocusOnTheBell(page);
}

/** The buttons at the end of the bar, as `data-testid`s, without the rows of an open «⋮». */
function endOfTheBar(page: Page): Promise<(string | null)[]> {
  return topbar(page)
    .locator('ion-buttons[slot=end]')
    .evaluate((group) =>
      [...group.querySelectorAll('ion-button')]
        .filter((button) => !button.closest('ion-popover') && button.getBoundingClientRect().width > 0)
        .map((button) => button.getAttribute('data-testid')),
    );
}

/** On a phone, «⋮» and the bell at the end of the bar and the title centred; «⋮» lists «Mis apps» and «Asistente», and
 *  each one opens. From a tablet, «Mis apps», the sparkles and the bell, all on the bar. */
async function expectTheBar(page: Page, size: (typeof SIZES)[number], shotOf: (state: string) => Promise<void>): Promise<void> {
  await expectTitleCentred(page, size.label);
  if (!compactBar(page)) {
    expect(await endOfTheBar(page)).toEqual(['topbar-apps', 'assistant-button', 'action-bell']);
    return;
  }
  expect(await endOfTheBar(page)).toEqual(['topbar-more', 'action-bell']);
  await topbarMore(page).click();
  await expect(topbarMoreMenu(page).locator('ion-button')).toHaveText(['Mis apps', 'Asistente']);
  await shotOf('bar-more');
  await page.keyboard.press('Escape');
  await expect(topbarMoreMenu(page)).toHaveCount(0);
  const sheet = await openApps(page);
  await sheet.locator('[data-testid=apps-launcher-close]').click();
  await expect(sheet).toHaveCount(0);
  const assistant = await openAssistant(page);
  await expect(assistant.locator('[data-testid=assistant-input] textarea')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(assistant).toHaveAttribute('data-open', 'false');
}

/** With the assistant open (beside the screen from a tablet), a new card comes in to its left and the panel opens
 *  over it. */
async function expectBesideTheAssistant(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  await clearItems(context, A);
  await bellSaysTheServer(page, context);
  await shown(page).locator('[data-testid=assistant-button]').click();
  const assistant = page.locator('[data-testid=assistant-panel]');
  await expect(assistant).toBeVisible();
  await noCardOnScreen(page);
  await raiseDemoNotice(context);
  const card = arrivalCard(page);
  await expect(card).toBeVisible();
  await card.hover();
  const [cardBox, assistantBox] = await Promise.all([card.boundingBox(), assistant.boundingBox()]);
  expect(cardBox!.x + cardBox!.width, 'the card to the left of the assistant').toBeLessThanOrEqual(assistantBox!.x + 1);
  await shotOf('assistant-arrival');
  await page.mouse.move(1, 1);
  await expect(card).toBeHidden({ timeout: 15_000 });
  const panel = await openActionCenter(page);
  const over = await page.evaluate(() => {
    const open = document.querySelector('[data-testid=action-panel]')?.shadowRoot?.querySelector('.modal-wrapper') as HTMLElement | null;
    const box = (open ?? document.querySelector('[data-testid=action-featured]'))!.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return hit?.closest('[data-testid=action-panel]') !== null;
  });
  expect(over, 'the panel over the assistant').toBe(true);
  await expect(featuredNotice(panel)).toBeVisible();
  await shotOf('assistant-panel');
  await closeActionCenter(page);
  await shown(page).locator('[data-testid=assistant-button]').click();
  await expect(assistant).toBeHidden();
}

/** A booking waiting for confirmation is told with the server's words: its heading, its sentence and «Confirmar las
 *  citas», and its deadline, the booking's start two days ahead, runs on the bell's ring. Confirmed, it goes. */
async function expectTheServersNotice(page: Page, context: BrowserContext, hour: string, shotOf: (state: string) => Promise<void>): Promise<void> {
  await noCardOnScreen(page);
  const booked = await post<{ id: string; status: string; start: string }>(context, '/appointment/appointments', {
    customer_id: salon.customer.id,
    services: [{ service_id: salon.service.id }],
    staff_id: salon.member.id,
    start: `${BOOKING_DAY}T${hour}`,
    source: 'whatsapp',
  });
  expect(booked.status).toBe('pending');
  await bellSaysTheServer(page, context);
  // A card under the pointer stays: the pointer goes to a corner no card covers.
  await page.mouse.move(1, 1);
  await noCardOnScreen(page);
  const counter = await serverCounter(context, 'appointment.to_confirm');
  const one = counter?.count === 1;
  expect(counter).toMatchObject({
    severity: 'warning',
    title: one ? '1 cita por confirmar' : `${counter?.count} citas por confirmar`,
    body: one
      ? 'Un cliente espera a que le confirmes la cita antes de que empiece.'
      : 'Tus clientes esperan a que les confirmes las citas antes de que empiecen.',
    action_label: 'Confirmar las citas',
  });
  expect(Date.parse(counter!.due!), 'the deadline: the start of the soonest booking waiting').toBeLessThanOrEqual(Date.parse(booked.start));
  const featured = await featureNotice(page, counter!.title);
  await expectTheServersWords(featured, counter!);
  expect(await bellRingLeft(page), 'the ring counts down to the booking').toBeLessThan(1);
  await shotOf('server-notice');
  await closeActionCenter(page);
  await post(context, '/appointment/appointments/confirm', { id: booked.id }, 200);
  await bellSaysTheServer(page, context);
}

/** At the till, with the charge sheet open, a new notice brings no card: the bell only counts it. */
async function expectQuietWhileCharging(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  await clearItems(context, A);
  await checkWithDish(page, context, 'es', dish);
  await bellSaysTheServer(page, context);
  await noCardOnScreen(page);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await raiseDemoNotice(context);
  // The card is offered in the same turn the bell takes the notice: once the bell counts it, no card means none came.
  await bellSaysTheServer(page, context);
  await expect(arrivalCard(page), 'no card while charging').toHaveCount(0);
  await shotOf('pos-checkout');
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();
}

/** «Configurar los datos del negocio» leads to the issuer; once it is saved, «Todavía no puedes facturar» goes. */
async function expectResolved(page: Page, context: BrowserContext, shotOf: (state: string) => Promise<void>): Promise<void> {
  const panel = await openActionCenter(page);
  await noticeButton(featuredNotice(panel), 'Configurar los datos del negocio').click();
  await expect(page).toHaveURL(/\/invoice\/issuer$/);
  await expect(actionPanel(page)).toBeHidden();
  const { legal_name, tax_id, address, postal_code, city, province, country } = original.configured ? original : { ...original, ...ISSUER };
  const saved = await api(context, A, 'POST', '/invoice/issuer', { legal_name, tax_id, address, postal_code, city, province, country });
  expect(saved.status).toBe(200);
  await bellSaysTheServer(page, context);
  await clearItems(context, A);
  const left = await bellSaysTheServer(page, context);
  if (left === 0) {
    await expect(actionBell(page)).not.toHaveClass(/has-notices/);
    await shotOf('bell-alone');
  }
  const opened = await openActionCenter(page);
  await expect(noticeIn(opened, BLOCKING)).toHaveCount(0);
  await closeActionCenter(page);
}

for (const [sizeIndex, size] of SIZES.entries()) {
  for (const [schemeIndex, scheme] of SCHEMES.entries()) {
    // A booking hour of its own per test: the professional is the same in every one.
    const hour = `${String(9 + sizeIndex * SCHEMES.length + schemeIndex).padStart(2, '0')}:00`;
    test(`BASE-F01 BASE-F10 at ${size.label}, ${scheme}: the bell, its arrivals and its panel`, async ({ browser }) => {
      test.setTimeout(300_000);
      const { context, page } = await spanishOwner(browser, size, scheme);
      const shotOf = (state: string) => captured(page, state, scheme, size.label);
      try {
        await clearItems(context, A);
        noPrintsWaiting();
        await page.reload();
        await bellSaysTheServer(page, context);
        await expect(actionBell(page)).toHaveAttribute('data-severity', 'danger');
        await shotOf('pill');
        await expectTheBar(page, size, shotOf);
        await expectArrival(page, context, shotOf);
        await expectThePanel(page, size, shotOf);
        await expectTheServersNotice(page, context, hour, shotOf);
        if (!compactBar(page)) await expectBesideTheAssistant(page, context, shotOf);
        await expectQuietWhileCharging(page, context, shotOf);
        await expectResolved(page, context, shotOf);
      } finally {
        await clearItems(context, A);
        await context.close();
        // The next run starts from a business that cannot issue invoices yet again.
        parkIssuerAgain();
      }
    });
  }
}

/** Hub `a` without an issuer again, keeping the one parked before the run. */
function parkIssuerAgain(): void {
  unparkIssuer(PARKED);
  parkIssuer(PARKED);
}
