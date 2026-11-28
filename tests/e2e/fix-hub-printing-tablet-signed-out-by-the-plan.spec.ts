// flow: PRINTING-F01 PRINTING-F18 BASE-F57
// On the Free plan (one device at a time), the bar tablet that prints loses its session when the owner enters on a
// browser. The owner's Printing → Printers then says on the receipts' card «Sesión cerrada» and why — never «Dispositivo
// apagado… enciéndelo» — and Printing → Devices marks the tablet and says why it prints nothing, in Spanish. When
// someone enters on the tablet again, its list no longer says it. Two browsers of `a`'s owner: the tablet sets itself up
// to print from itself (its `X-Device-Id`, as the app does) and the browser's entry ends its session for real. The
// minute and the 90 s are not waited for: `psql()` moves the receipt and the tablet's last news back. `a`'s photo gets
// the Free plan's one device for this spec and is put back after. Captures at the three sizes. What it makes is
// «e2e Signed out …», deleted before and after.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { dropPlanFromPhoto, restorePhotoFrom } from './business';
import { A, api, login, OWNER, psql, shown } from './helpers';
import { fleetShots, forgetDevices, printHostHello } from './printing-helpers';
import { stamp } from './sale-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-HUB-PRINTING-TABLET-SIGNED-OUT-BY-THE-PLAN';
const TAG = 'e2e Signed out';
const RUN = stamp();
/** Where `a`'s photo waits while this spec gives it the Free plan's one device. */
const KEPT = 'e2e_backup_photo_signed_out_by_the_plan';
/** The tablet's own id, as its app names it (`X-Device-Id`). */
const TABLET = `${TAG} tablet ${RUN}`;
/** Longer than the card's reading by the clock (30 s) and a read. */
const BY_THE_CLOCK = { timeout: 45_000 };

function cleanUp(): void {
  psql(`delete from printing_printjob where printer_id in (select id from printing_printer where name like '${TAG} %')`);
  forgetDevices(`${TAG} %`, { names: [`${TAG} %`] });
  psql(`delete from printing_printer where name like '${TAG} %'`);
}

test.beforeAll(() => {
  cleanUp();
  dropPlanFromPhoto(KEPT);
  psql(
    "update base_hub set state = state || jsonb_build_object('plan', jsonb_build_object('slug', 'free', 'max_devices', 1)) " +
      "where slug = 'a'",
  );
});

test.afterAll(() => {
  restorePhotoFrom(KEPT);
  cleanUp();
});

/** `a`'s owner entering on a browser of their own, in Spanish: a new device of the hub, never another one's session. */
async function ownerOn(browser: Browser, next: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next, OWNER, { fresh: true });
  // The entry sets the account's language; the pages opened after it are in Spanish.
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  return { context, page };
}

/** Sets the tablet up with `printer`, from the tablet itself (its `X-Device-Id`), as Devices does in the app. */
async function setUpTablet(context: BrowserContext, printer: string): Promise<string> {
  const host = new URL(A).hostname;
  const csrf = (await context.cookies(A)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value ?? '';
  const res = await context.request.post(`${A}/api/printing/devices`, {
    headers: { 'X-CSRFToken': csrf, Accept: 'application/json', 'X-Device-Id': TABLET },
    data: { name: `${TAG} Barra ${RUN}`, printers: [printer] },
  });
  expect(res.status(), await res.text()).toBe(201);
  const row = (await res.json()) as { id: string; signed_out: boolean };
  expect(row.signed_out, 'just set up from the tablet: its session is open').toBe(false);
  return row.id;
}

/** Whether the tablet's browser still has a session on `a`. */
async function signedIn(context: BrowserContext): Promise<boolean> {
  const me = await context.request.get(`${A}/api/me`, { headers: { Accept: 'application/json' } });
  return ((await me.json()) as { user: unknown }).user !== null;
}

/** The tablet as if it went quiet 2 min ago, with the receipt waiting as long. */
function quietForTwoMinutes(job: string): void {
  psql(`update printing_printdevice set last_seen_at = now() - interval '2 minutes' where key = encode(sha256('${TABLET}'::bytea), 'hex')`);
  psql(`update printing_printjob set created_at = now() - interval '2 minutes' where id = '${job}'`);
}

test('PRINTING-F01: the owner entering on a browser closes the tablet’s session, and Printing says so', async ({ browser }) => {
  // Three real entries through erplora.com, each a trip there and back.
  test.setTimeout(300_000);
  const tablet = await ownerOn(browser, '/printing/devices');
  let owner: { context: BrowserContext; page: Page } | null = null;
  try {
    const created = await api<{ id: string }>(tablet.context, A, 'POST', '/printing/printers', {
      name: `${TAG} Caja ${RUN}`,
      kind: 'network',
      address: '10.0.0.79',
      usage: 'receipt',
    });
    expect(created.status, JSON.stringify(created.data)).toBe(201);
    const printer = created.data.id;
    const device = await setUpTablet(tablet.context, printer);
    const queued = await api<{ job: { id: string } }>(tablet.context, A, 'POST', '/printing/jobs', {
      document_type: 'receipt',
      document: { business_name: 'e2e', receipt_id: `T-${RUN}`, items: [{ name: 'Caña', quantity: 1, total: 2.5 }], total: 2.5 },
      job_key: `${TAG} ${RUN}`,
      printer,
    });
    expect(queued.status, JSON.stringify(queued.data)).toBe(201);

    // The owner opens the business on a browser: one device at a time, so the tablet's session ends.
    owner = await ownerOn(browser, '/printing/printers');
    expect(await signedIn(tablet.context), 'the tablet is out').toBe(false);
    quietForTwoMinutes(queued.data.job.id);

    // The receipts' card says the real cause, by the clock, and never «switch it on».
    const page = owner.page;
    await page.goto(`${A}/printing/printers`);
    await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
    const card = shown(page).locator('[data-testid=printing-summary-card-receipt]');
    await expect(card).toContainText('Sesión cerrada', BY_THE_CLOCK);
    await expect(shown(page).locator('[data-testid=printing-summary-signed-out-receipt]')).toHaveText(
      'El dispositivo que lo imprime perdió la sesión al entrar alguien en otro: tu plan no cubre más dispositivos a la vez. Vuelve a entrar en él, o amplía los dispositivos de tu plan.',
    );
    await expect(shown(page).locator('[data-testid=printing-summary-device-off-receipt]')).toHaveCount(0);
    await fleetShots(page, `${KEY}-printers`, async (p) => {
      await expect(shown(p).locator('[data-testid=printing-summary-signed-out-receipt]')).toBeVisible();
    });

    // Devices marks the tablet and says why it prints nothing.
    await page.goto(`${A}/printing/devices`);
    const notice = shown(page).locator(`[data-testid=printing-devices-signed-out-${device}]`);
    await expect(notice).toContainText(`«${TAG} Barra ${RUN}» no imprime: perdió la sesión al entrar alguien en otro dispositivo.`);
    await expect(notice).toContainText('Tu plan no cubre más dispositivos a la vez: vuelve a entrar en él, o amplía los dispositivos de tu plan.');
    await expect(shown(page).locator(`[data-testid=printing-devices-name-${device}]`).first()).toContainText('Sesión cerrada');
    await fleetShots(page, `${KEY}-devices`, async (p) => {
      await expect(shown(p).locator(`[data-testid=printing-devices-signed-out-${device}]`)).toBeVisible();
    });

    // On the tablet, its Access page says why it is out and waits; someone enters with their account again (still
    // signed in on erplora.com, the trip comes straight back): it is no longer signed out, and, one device at a time,
    // the browser is.
    await tablet.page.goto(`${A}/printing/devices`);
    await expect(shown(tablet.page).getByTestId('access-notice')).toContainText('Sesión abierta en otro dispositivo');
    await shown(tablet.page).getByTestId('access-account').click();
    await expect(tablet.page).toHaveURL(`${A}/printing/devices`, { timeout: 60_000 });
    expect(await signedIn(tablet.context)).toBe(true);
    // Its app connects to print again, as after every entry: Printing notes the session it prints with now.
    await printHostHello(tablet.page, TABLET, printer);
    await tablet.page.reload();
    await expect(shown(tablet.page).locator(`[data-testid=printing-devices-name-${device}]`).first()).toBeVisible();
    await expect(shown(tablet.page).locator(`[data-testid=printing-devices-signed-out-${device}]`)).toHaveCount(0);
    await expect(shown(tablet.page).locator(`[data-testid=printing-devices-name-${device}]`).first()).not.toContainText('Sesión cerrada');
  } finally {
    await tablet.page.evaluate(() => (window as unknown as { printSocket?: WebSocket }).printSocket?.close()).catch(() => undefined);
    await owner?.context.close();
    await tablet.context.close();
  }
});
