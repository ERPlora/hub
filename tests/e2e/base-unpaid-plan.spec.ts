// flow: BASE-F117
// The bell's notice of an unpaid invoice of the plan, as the owner of hub `a` meets it in Spanish at 375, 820 and
// 1440: erplora.com's photo says the payment is pending and when the business is suspended, the notice comes as a card
// without reloading and says it with the date, its button opens the business's unpaid invoices on erplora.com outside
// the hub, past the deadline it says the deadline went by with the ring empty, an employee never sees it, and once paid
// it goes without reloading. The photo is sent the way erplora.com sends it (`PUT /internal/hubs/{id}/state`, signed)
// and `a`'s photo is put back after the run.
import { expect, type Page, test } from '@playwright/test';

import {
  arrivalCard,
  bellRingLeft,
  bellSays,
  bellTotal,
  closeActionCenter,
  expectTheServersWords,
  featureNotice,
  noticeButton,
  serverCounter,
} from './action-center';
import { capture, EMPLOYEE, horizontalOverflow, internalPut, psql, saveSessionForTheSweep } from './helpers';
import { spanishPerson } from './home-helpers';
import { STACK } from './stack';

const KEY = 'base.payment_pending';
const TITLE = 'Tu plan de ERPlora tiene una factura sin pagar';
const PAY = 'Pagar en erplora.com';
const SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1440, height: 900 },
] as const;
const DAY_MS = 86_400_000;
/** The copy the run keeps of `a`'s photo. */
const BACKUP = 'e2e_base_unpaid_plan_photo';

let hubId = '';
/** Monotonic photo versions: an older one changes nothing. */
let version = Math.floor(Date.now() / 1000);

/** erplora.com's photo of `a`: its status and, with a payment pending, the instant it is suspended. */
async function photo(status: 'active' | 'past_due', suspendsOn?: Date): Promise<void> {
  version += 1;
  const body = { hub_id: hubId, slug: 'a', version, status, ...(suspendsOn ? { suspends_on: suspendsOn.toISOString() } : {}) };
  const response = await internalPut(`/internal/hubs/${hubId}/state`, JSON.stringify(body));
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

const inDays = (days: number): Date => new Date(Date.now() + days * DAY_MS);

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  hubId = psql("select id from base_hub where slug = 'a'");
  expect(hubId, `the registry of ${STACK.database} has hub a`).toMatch(/^[0-9a-f-]{36}$/);
  version = Math.max(version, Number(psql(`select state_version from base_hub where id = '${hubId}'`)));
  psql([`drop table if exists ${BACKUP}`, `create table ${BACKUP} as select id, state, state_version from base_hub where id = '${hubId}'`].join('; '));
});

test.afterAll(() => {
  psql([`update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP} b where b.id = h.id`, `drop table ${BACKUP}`].join('; '));
});

async function snap(page: Page, name: string, width: number): Promise<void> {
  expect(await horizontalOverflow(page), `${name} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `BASE-F117-${name}-${width}`);
}

for (const size of SIZES) {
  test(`at ${size.width}: the notice comes with its deadline, leads to the invoices and goes once paid`, async ({ browser }) => {
    await photo('active');
    const { context, page } = await spanishPerson(browser, size);
    try {
      // The bell's first result is in: what comes after it arrives as a card.
      await bellSays(page, await bellTotal(context));
      await photo('past_due', inDays(3));
      await expect(arrivalCard(page)).toContainText(TITLE);
      await expect(arrivalCard(page)).toHaveCount(0, { timeout: 15_000 });

      const counter = await serverCounter(context, KEY);
      expect(counter?.severity).toBe('danger');
      expect(counter?.body).toMatch(/^Págala en erplora\.com: si no se paga antes del \d{1,2} de \w+ de \d{4}, el negocio se suspende\. No se borra nada\.$/);
      const featured = await featureNotice(page, TITLE);
      await expectTheServersWords(featured, counter!);
      const left = await bellRingLeft(page);
      expect(left).toBeGreaterThan(0.3);
      expect(left).toBeLessThan(0.6);
      await snap(page, 'pending', size.width);

      let opened = '';
      await context.route(`${STACK.saas}/dashboard/billing/**`, async (route) => {
        opened = route.request().url();
        await route.fulfill({ status: 200, contentType: 'text/html', body: '<p>billing</p>' });
      });
      await noticeButton(featured, PAY).click();
      await expect.poll(() => opened).toBe(`${STACK.saas}/dashboard/billing/invoices?business=${hubId}&status=open`);
      await page.bringToFront();

      const pending = await bellTotal(context);
      await bellSays(page, pending);
      await photo('active');
      await bellSays(page, pending - 1);
      expect(await serverCounter(context, KEY)).toBeUndefined();
    } finally {
      await context.close();
    }
  });
}

test('past its deadline and not yet suspended, the notice says the deadline went by', async ({ browser }) => {
  await photo('past_due', new Date(Date.now() - 60 * 60 * 1000));
  const { context, page } = await spanishPerson(browser, SIZES[2]);
  try {
    const counter = await serverCounter(context, KEY);
    expect(counter?.body).toMatch(/^Págala en erplora\.com: su plazo terminó el \d{1,2} de \w+ de \d{4} y el negocio se puede suspender en cualquier momento\. No se borra nada\.$/);
    const featured = await featureNotice(page, TITLE);
    await expectTheServersWords(featured, counter!);
    expect(await bellRingLeft(page)).toBe(0);
    await snap(page, 'overdue', SIZES[2].width);
    await closeActionCenter(page);
    await saveSessionForTheSweep(context);
  } finally {
    await context.close();
  }
});

test('an employee never sees it', async ({ browser }) => {
  await photo('past_due', inDays(3));
  const { context, page } = await spanishPerson(browser, SIZES[2], EMPLOYEE);
  try {
    expect(await serverCounter(context, KEY)).toBeUndefined();
    await expect(page.locator('[data-testid=action-bell]').first()).toBeVisible();
  } finally {
    await context.close();
  }
});
