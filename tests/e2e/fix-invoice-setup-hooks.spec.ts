// flow: INVOICE-F14 INVOICE-F21
// Invoicing's steps of the Home (FIX-INVOICE-SETUP-HOOKS; the old hub's ⛔ «Your business details» and the old module's
// `setup`, the old dashboard in docs/reference/old-hub/dashboard-*.png), as hub `a` reads them in Spanish: with no
// issuer, the owner has «Los datos de tu negocio» pending and «Necesario para facturar» in «Termina de configurar tu
// negocio»; its «Configurar» leads to Invoicing → Issuer and, once the legal name, tax ID and address are saved there,
// the step is done without a reload. «Tu numeración de facturas» is «Recomendado» and pending while the business has no
// series, and done without a reload once it has one; an employee is told about the ⛔ without «Configurar» (and the red
// strip of the other screens says who has to set it up, gh:hub#2567) and never about the numbering. On Invoices and
// Series the red strip is the one notice: Invoicing does not say it again under it, and it goes, without a reload,
// once the issuer is saved (FIX-HUB-INVOICE-TWO-NEAR-IDENTICAL-BUSINESS-DATA-NOTICES). Captures
// `FIX-INVOICE-SETUP-HOOKS-INVOICE-F21-<width>` (the ⛔), `…-INVOICE-F14-<width>` (the numbering) and
// `FIX-HUB-INVOICE-TWO-NEAR-IDENTICAL-BUSINESS-DATA-NOTICES-[series-]<width>` (Invoices and Series with no issuer).
// The hub's issuer row is parked for the run and put back as it was after it (other specs need it); the run's own
// series are `E2E…`, which the cleanup removes.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, login, OWNER, psql, shot, shown, untilStill } from './helpers';
import { stamp, VIEWPORTS } from './inventory-helpers';
import { ensureIssuer } from './invoice-helpers';

const KEY = 'FIX-INVOICE-SETUP-HOOKS';
/** The task that left the red strip as the one notice of Invoices and Series. */
const ONE_NOTICE = 'FIX-HUB-INVOICE-TWO-NEAR-IDENTICAL-BUSINESS-DATA-NOTICES';
/** Base's strip title, the words both notices said. */
const CANNOT_INVOICE = 'Todavía no puedes facturar';
const IDENTITY = 'invoice.business_identity';
const NUMBERING = 'invoice.numbering';
/** The hub's issuer, parked while the run needs a hub without one. */
const PARKED = 'e2e_fix_inv_hooks_issuer';
const RUN = stamp();
const ISSUER = {
  'legal-name': 'e2e Peluquería Ana SL',
  'tax-id': 'B12345674',
  address: 'Calle Mayor 1',
  'postal-code': '28001',
  city: 'Madrid',
  province: 'Madrid',
};

interface NumberingStatus {
  total_series: number;
}

test.describe.configure({ mode: 'serial' });

/** The run's own series (`E2E…`), which number nothing: the business's numbering as the run found it. */
const OWN_SERIES = `delete from invoice_invoiceseries s where s.code like 'E2E%' and not exists (select 1 from invoice_invoice i where i.series_id = s.id)`;

/** No issuer at all: what a new business has before it sets one up. */
function noIssuer(): void {
  psql('delete from invoice_issuer');
}

test.beforeAll(() => {
  psql([`drop table if exists ${PARKED}`, `create table ${PARKED} as select * from invoice_issuer`].join('; '));
  noIssuer();
});

test.afterAll(() => {
  psql(
    [
      OWN_SERIES,
      'delete from invoice_issuer',
      `insert into invoice_issuer select * from ${PARKED}`,
      `drop table ${PARKED}`,
    ].join('; '),
  );
});

/** A person of `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function spanish(
  browser: Browser,
  viewport: { width: number; height: number },
  who: Credentials = OWNER,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/', who);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  // The person's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const row = (page: Page, key: string): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${key}"]`);
const pill = (page: Page, key: string): Locator => row(page, key).locator('[data-testid="setup-pill"]');
const configure = (page: Page, key: string): Locator => row(page, key).locator(`[data-testid="setup-configure-${key}"]`);

/** «Ver todo»: the list folds what does not fit while steps are pending. */
async function unfolded(page: Page): Promise<void> {
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = card(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
}

/** How many series the business has: the numbering step waits only while it has none. */
async function seriesNow(context: BrowserContext): Promise<number> {
  const res = await api<NumberingStatus>(context, A, 'GET', '/invoice/numbering/status');
  expect(res.status).toBe(200);
  return res.data.total_series;
}

/** Marks the page: a reload clears it, so a step that turns «Hecho» with the mark still there did it live. */
async function markNoReload(page: Page): Promise<void> {
  await page.evaluate(() => Object.assign(window, { __e2eNoReload: true }));
}

/** The lines a text takes on screen: the distinct tops of its line boxes. */
async function lines(text: Locator): Promise<number> {
  return text.evaluate((element) => {
    const range = document.createRange();
    range.selectNodeContents(element);
    return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size;
  });
}

async function expectNoReload(page: Page): Promise<void> {
  expect(await page.evaluate(() => (window as { __e2eNoReload?: boolean }).__e2eNoReload === true)).toBe(true);
}

test('INVOICE-F21: «Los datos de tu negocio» is the ⛔ while there is no issuer, «Configurar» leads to the issuer and saving it ticks it live', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 });
  try {
    await expect(row(page, IDENTITY).locator('.setup-row-title')).toHaveText('Los datos de tu negocio');
    await expect(row(page, IDENTITY).locator('.setup-row-desc')).toHaveText('Razón social, NIF y domicilio: sin ellos no puedes emitir una factura.');
    await expect(pill(page, IDENTITY)).toHaveText('Necesario para facturar');

    // «Configurar» leads to Invoicing → Issuer, inside the app: no reload on the way.
    await markNoReload(page);
    await configure(page, IDENTITY).click();
    await expect(page).toHaveURL(`${A}/invoice/issuer`);
    const form = shown(page);
    await expect(form.locator('[data-testid=invoice-issuer-missing]')).toBeVisible();
    for (const [hook, value] of Object.entries(ISSUER)) await form.locator(`[data-testid=invoice-issuer-${hook}] input`).fill(value);
    await form.locator('[data-testid=invoice-issuer-save]').click();
    await expect(page.locator('ion-toast').filter({ hasText: 'Emisor guardado.' })).toBeVisible();

    // Back on the Home, the step is done without a reload (it leaves the folded list; «Ver todo» says «Hecho»).
    await page.goBack();
    await expect(page).toHaveURL(`${A}/`);
    await expect(card(page)).toHaveAttribute('aria-busy', 'false');
    await unfolded(page);
    await expect(pill(page, IDENTITY)).toHaveText('Hecho');
    await expect(configure(page, IDENTITY)).toHaveCount(0);
    await expectNoReload(page);
  } finally {
    await context.close();
    noIssuer();
  }
});

test('INVOICE-F14: «Tu numeración de facturas» is recommended while the business has no series and done once it has one', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 });
  try {
    const series = await seriesNow(context);
    await unfolded(page);
    test.info().annotations.push({ type: 'series at start', description: String(series) });
    if (series > 0) {
      // A business that already numbers (its series were born with its first document) has nothing to check.
      await expect(pill(page, NUMBERING)).toHaveText('Hecho');
      return;
    }
    await expect(row(page, NUMBERING).locator('.setup-row-title')).toHaveText('Tu numeración de facturas');
    await expect(row(page, NUMBERING).locator('.setup-row-desc')).toHaveText(
      'Antes de tu primera venta, revisa el prefijo con el que saldrán tus números de factura. Si vienes de otro sistema, continúa su numeración en vez de empezar otra vez por el 1.',
    );
    await expect(pill(page, NUMBERING)).toHaveText('Recomendado');
    // Reading the step never opens the year's series.
    expect(await seriesNow(context)).toBe(0);

    // «Configurar» leads to Invoicing → Series.
    await configure(page, NUMBERING).click();
    await expect(page).toHaveURL(`${A}/invoice/series`);
    await page.goBack();
    await expect(page).toHaveURL(`${A}/`);
    await markNoReload(page);

    // A series of its own (continuing another system's numbering): the step is done without a reload.
    const year = new Date().getFullYear();
    const created = await api(context, A, 'POST', '/invoice/series', {
      code: `E2E${RUN}`.slice(0, 20).toUpperCase(),
      name: 'e2e series',
      invoice_type: 'F1',
      year,
      next_number: 1201,
    });
    expect(created.status).toBe(201);
    await unfolded(page);
    await expect(pill(page, NUMBERING)).toHaveText('Hecho');
    await expect(configure(page, NUMBERING)).toHaveCount(0);
    await expectNoReload(page);
  } finally {
    await context.close();
    psql(OWN_SERIES);
  }
});

test('INVOICE-F21 and INVOICE-F14: an employee is told about the ⛔ without «Configurar», and never about the numbering', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 390, height: 844 }, EMPLOYEE);
  try {
    await unfolded(page);
    await expect(pill(page, IDENTITY)).toHaveText('Necesario para facturar');
    await expect(configure(page, IDENTITY)).toHaveCount(0);
    await expect(row(page, IDENTITY).locator(`[data-testid="setup-note-${IDENTITY}"]`)).toHaveText('Esto lo tiene que configurar un administrador.');
    await expect(row(page, NUMBERING)).toHaveCount(0);

    // Any other screen: the red strip says it, whole, on a phone (gh:hub#2567).
    await page.goto(`${A}/invoice/invoices`);
    const strip = shown(page).locator('[data-testid="blocking-strip"]');
    await expect(strip).toBeVisible();
    await expect(strip).toContainText('Los datos de tu negocio');
    await expect(strip).toContainText('Esto lo tiene que configurar un administrador.');
    await expect(strip.locator(`[data-testid="blocking-configure-${IDENTITY}"]`)).toHaveCount(0);
    // The one notice: Invoicing does not say it again under the strip, so who has to set it up is said once.
    await expect(shown(page).locator('[data-testid="invoice-issuer-notice"]')).toHaveCount(0);
    await expect(shown(page).getByText(CANNOT_INVOICE, { exact: true })).toHaveCount(1);
    await expect(shown(page).getByText('Esto lo tiene que configurar un administrador.', { exact: true })).toHaveCount(1);
    // On a phone the note reads whole, never a narrow column broken into three lines.
    expect(await lines(strip.locator('.blocking-strip-note')), 'the note in at most two lines').toBeLessThanOrEqual(2);
    await untilStill(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'no sideways scroll at 390').toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot(`${KEY}-INVOICE-F21-employee-390`) });
  } finally {
    await context.close();
  }
});

for (const size of VIEWPORTS) {
  test(`INVOICE-F21 and INVOICE-F14 at ${size.label}: the ⛔ and the numbering pending as the owner reads them`, async ({ browser }) => {
    const { context, page } = await spanish(browser, { width: size.width, height: size.height });
    try {
      const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      await expect(pill(page, IDENTITY)).toHaveText('Necesario para facturar');
      await row(page, IDENTITY).evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-INVOICE-F21-${size.label}`) });

      await unfolded(page);
      await expect(pill(page, NUMBERING)).toHaveText((await seriesNow(context)) > 0 ? 'Hecho' : 'Recomendado');
      await row(page, NUMBERING).evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-INVOICE-F14-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}

// flow: INVOICE-F21
for (const size of VIEWPORTS) {
  test(`INVOICE-F21 at ${size.label}: Invoices and Series say once that nothing can be invoiced, and nothing once the issuer is saved`, async ({ browser }) => {
    const { context, page } = await spanish(browser, { width: size.width, height: size.height });
    try {
      for (const [screen, name] of [['invoices', ONE_NOTICE], ['series', `${ONE_NOTICE}-series`]] as const) {
        await page.goto(`${A}/invoice/${screen}`);
        const strip = shown(page).locator('[data-testid="blocking-strip"]');
        await expect(strip).toBeVisible();
        await expect(strip).toContainText('Los datos de tu negocio');
        await expect(strip.locator(`[data-testid="blocking-configure-${IDENTITY}"]`)).toHaveText('Configurar');
        // One red notice on the screen, whatever its words: the strip, and none of Invoicing's own under it.
        await expect(shown(page).getByText(CANNOT_INVOICE, { exact: true })).toHaveCount(1);
        await expect(shown(page).locator('[data-testid="blocking-strip"], .inline-feedback[data-tone="danger"]')).toHaveCount(1);
        await expect(shown(page).locator('[data-testid="invoice-issuer-notice"]')).toHaveCount(0);
        await untilStill(page);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: shot(`${name}-${size.label}`) });
      }

      // Saved anywhere (another device, here the API), the strip leaves Series without a reload, and Invoices with it.
      await markNoReload(page);
      await ensureIssuer(context);
      await expect(shown(page).locator('[data-testid="blocking-strip"]')).toHaveCount(0);
      await expect(shown(page).getByText(CANNOT_INVOICE, { exact: true })).toHaveCount(0);
      await expectNoReload(page);
      await page.goto(`${A}/invoice/invoices`);
      await expect(shown(page).locator('[data-testid=invoice-list-row], [data-testid=invoice-list-empty]').first()).toBeVisible();
      await expect(shown(page).getByText(CANNOT_INVOICE, { exact: true })).toHaveCount(0);
      await expect(shown(page).locator('[data-testid="blocking-strip"], .inline-feedback[data-tone="danger"]')).toHaveCount(0);
    } finally {
      await context.close();
      noIssuer();
    }
  });
}
