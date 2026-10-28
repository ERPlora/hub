// Rectifying an invoice by asking the assistant (INVOICE-F08; PLAN §30, the second of the «Cinco acciones de IA
// pulidas»: the rectifying invoice, with the new invoice in preview before its confirmation), end to end with its real
// dependencies: the Hub of this stack, its SaaS's gateway (`/internal/assistant/*`) and the e2e's provider
// (assistant-provider.ts, its marker `E2E-RECTIFY <number> … porque <reason>`), which reads the rectification's preview,
// says it and asks to rectify the invoice it named. The SaaS must be seeded with that provider (README «El asistente»).
// The owner, with an invoice issued, asks «rectifica la factura <number> porque el precio estaba mal»: the preview comes
// first (the original, the type, the reason, the next number of the series, the amounts in negative), then the dangerous
// card, which carries it too in «What will happen» (the type, the next number, the amounts in negative as money:
// FIX-HUB-INVOICE-ASSISTANT-RECTIFY-CARD-WITHOUT-PREVIEW, through base's preview, BASE-F98); «Cancel» issues nothing and
// the original stays issued, typing the word issues it and «Invoices» shows the original cancelled and the new
// rectifying one dated today. Asked to rectify a rectifying invoice, the assistant says why and offers no card.
// Nothing reaches VeriFactu's tax agency: issuing seals the record locally (no transmission in this stack).
// What this file creates is deleted after it (its invoices, their records, the numbering as found).
// flow: INVOICE-F08
// flow: BASE-F97 (the card and its receipt name the action: «Rectify in Invoicing», «Rectificar en Facturación»;
// FIX-HUB-BASE-ASSISTANT-CARD-RECTIFY-SAYS-DO-THIS-IN-INVOICING, it said «Do this»)
import { execSync } from 'node:child_process';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { A, api, compactBar, login, registerBusinessIn, registrationOf, REPO_DIR, shot, shown, untilStill } from './helpers';
import { cleanInvoices, ensureIssuer, type InvoiceOut, invoiceOf, issuedIds, snapshotSeries } from './invoice-helpers';
import { stamp } from './sale-helpers';
import { STACK } from './stack';

const KEY = 'FIX-INVOICE-NO-VOICE-RECTIFY-WITH-ASSISTANT';
const RUN = stamp();
const REASON = 'el precio estaba mal';
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

let provider: Provider;

interface Preview {
  original: { number: string; total_amount: number; remaining: number };
  invoice_type: string;
  next_number: string;
  issue_date: string;
  base_amount: number;
  tax_amount: number;
  total_amount: number;
}

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** The month's assistant messages of the business `a` back to none: a run never spends the plan's allowance. */
function unspend(): void {
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

/** An invoice (F1) issued by hand, 100.00 € + 21 % VAT, recorded for the cleanup. */
/** The preview the Hub gives for rectifying `number` (server-side evidence of what the assistant and its card say). */
async function previewOf(context: BrowserContext, number: string): Promise<Preview> {
  const path = `/invoice/invoices/rectification_preview?number=${encodeURIComponent(number)}&reason=${encodeURIComponent(REASON)}`;
  const read = await api<Preview>(context, A, 'GET', path);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  return read.data;
}

async function anInvoice(context: BrowserContext): Promise<InvoiceOut> {
  const created = await api<InvoiceOut>(context, A, 'POST', '/invoice/invoices', {
    lines: [{ description: `e2e Corte ${RUN}`, quantity: '1', unit_price: 10000, tax_rate: '21' }],
    customer_name: `e2e Talleres ${RUN}`,
    customer_tax_id: 'B12345674',
    customer_address: 'Calle Luna 3, Madrid',
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  issuedIds.add(created.data.id);
  return created.data;
}

test.beforeAll(async ({ browser }) => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices');
  snapshotSeries();
  await ensureIssuer(context);
  await context.close();
});

test.afterAll(async () => {
  await provider?.close();
  try {
    cleanInvoices();
  } finally {
    unspend();
  }
});

test.beforeEach(() => {
  unspend();
});

// ── The assistant's panel (as base-assistant.spec.ts drives it) ──

const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const lastAnswer = (page: Page): Locator => panel(page).locator('[data-testid="assistant-bubble-assistant"]').last();
const receipts = (page: Page): Locator => panel(page).locator('[data-testid="assistant-receipt"]');
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

async function openPanel(page: Page): Promise<void> {
  await expect(opener(page)).toBeVisible();
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/** Writes `text` and sends it with Enter, without waiting for the turn to end (a card stops it half-way). */
async function ask(page: Page, text: string): Promise<void> {
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  const before = await answers(page).count();
  await box(page).fill(text);
  await box(page).press('Enter');
  await expect(answers(page)).toHaveCount(before + 1);
}

async function decide(page: Page, button: 'submit' | 'cancel'): Promise<void> {
  await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
  await expect(card(page)).toBeHidden();
}

/** What the model was told of the preview: the last tool result the gateway sent the provider, as sent. */
function toldPreview(): Record<string, unknown> {
  const chat = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').at(-1)?.body;
  const messages = (chat?.messages ?? []) as { role: string; content?: unknown }[];
  return JSON.parse(String(messages.filter((message) => message.role === 'tool').at(-1)?.content ?? '{}')) as Record<string, unknown>;
}

const euros = (cents: number) => `${(cents / 100).toFixed(2)} €`;
const previewBlock = (page: Page): Locator => card(page).locator('[data-testid="assistant-confirm-preview"]');
const asked = (number: string) => `E2E-RECTIFY ${number} rectifica la factura ${number} porque ${REASON}`;

test('INVOICE-F08 — «rectify invoice <number> because the price was wrong»: the preview first, then the dangerous card; «Cancel» issues nothing, the typed word issues it', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  const context = page.context();
  const invoice = await anInvoice(context);
  // The preview the Hub gives for it, read before (server-side evidence of what the assistant must say).
  const expected = await previewOf(context, invoice.number);
  expect([expected.invoice_type, expected.total_amount]).toEqual(['R1', -12100]);

  await openPanel(page);
  await ask(page, asked(invoice.number));
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  // The preview, before the card: the original, the type, the reason, the next number and the amounts in negative.
  const preview = lastAnswer(page);
  await expect(preview.locator('strong').first()).toHaveText(invoice.number);
  await expect(preview).toContainText(`e2e Talleres ${RUN}`);
  await expect(preview).toContainText('Tipo: R1');
  await expect(preview).toContainText(`Motivo: ${REASON}`);
  await expect(preview).toContainText(`Número: ${expected.next_number} (el siguiente de la serie RECT; se asigna al emitirla)`);
  await expect(preview).toContainText(`Base: ${euros(-10000)}`);
  await expect(preview).toContainText(`Impuestos: ${euros(-2100)}`);
  await expect(preview).toContainText(`Total: ${euros(-12100)}`);
  // The preview was the Hub's own reading, sent to the model as it is: never a figure the model made up.
  expect(toldPreview()).toMatchObject({
    original: { number: invoice.number, total_amount: 12100, remaining: 12100 },
    invoice_type: 'R1',
    next_number: expected.next_number,
    total_amount: -12100,
  });
  // Reading it issued nothing; the card is the dangerous one, naming the invoice and the reason.
  expect((await invoiceOf(context, invoice.id)).status).toBe('issued');
  await expect(card(page)).toContainText('Rectify in Invoicing. Check each datum before going on.');
  await expect(card(page)).toContainText(`Number: ${invoice.number}`);
  await expect(card(page)).toContainText(`Reason: ${REASON}`);
  // And what it will do: the rectifying invoice of that preview, its amounts as money (EUR, the business's currency).
  await expect(previewBlock(page)).toContainText('What will happen');
  await expect(previewBlock(page).locator('li')).toHaveText([
    'Type of rectifying invoice: R1',
    `Next number: ${expected.next_number}`,
    'Tax base: -€100.00',
    'Tax: -€21.00',
    'Total: -€121.00',
  ]);
  const submit = card(page).locator('[data-testid="assistant-confirm-submit"] button');
  await expect(submit).toBeDisabled();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toBeVisible();
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // «Cancel»: nothing is issued and the original stays issued.
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await expect(receipts(page).last()).toHaveText('Not done, cancelled: Rectify in Invoicing');
  const cancelled = await invoiceOf(context, invoice.id);
  expect([cancelled.status, cancelled.rectifications]).toEqual(['issued', []]);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await openPanel(page);
    await preview.scrollIntoViewIfNeeded();
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-preview-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // Asked again, the word typed: the rectifying invoice the preview said is issued, as the person.
  await ask(page, asked(invoice.number));
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await card(page).locator('[data-testid="assistant-confirm-input"] input').fill('confirm');
  await expect(submit).toBeEnabled();
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText('Hecho.');
  await expect(receipts(page).last()).toHaveText('Done: Rectify in Invoicing');
  const after = await invoiceOf(context, invoice.id);
  expect(after.status).toBe('cancelled');
  expect(after.rectifications).toHaveLength(1);
  const rectifying = (await invoiceOf(context, after.rectifications[0].id)) as InvoiceOut & { issue_date: string };
  issuedIds.add(rectifying.id);
  expect([rectifying.number, rectifying.invoice_type, rectifying.total_amount, rectifying.rectifies?.number]).toEqual([
    expected.next_number,
    'R1',
    -12100,
    invoice.number,
  ]);

  // «Invoices» shows the original cancelled and the new rectifying one, dated today (the panel stays docked beside it).
  await page.goto(`${A}/invoice/invoices`);
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  const original = shown(page).locator('[data-testid=invoice-list-row]', { hasText: invoice.number }).first();
  await expect(original).toContainText('Cancelled');
  const born = shown(page).locator('[data-testid=invoice-list-row]', { hasText: rectifying.number }).first();
  const [year, month, dayOf] = expected.issue_date.split('-');
  await expect(born).toContainText(`${Number(month)}/${Number(dayOf)}/${year}`);
  await expect(born).toContainText(/-\s?€?\s?121[.,]00/);
  expect(rectifying.issue_date).toBe(expected.issue_date);
  // Its page: a rectifying invoice (R1) that links the invoice it rectifies.
  await born.click();
  await page.waitForURL(new RegExp(`/invoice/invoices/${rectifying.id}$`));
  await expect(shown(page).locator('[data-testid=invoice-detail-type]')).toHaveText('Rectifying (R1)');
  await expect(shown(page).locator('[data-testid=invoice-detail-rectifies-link]')).toHaveText(invoice.number);
  // The owner's session, with the assistant docked, for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`).
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
});

// FIX-HUB-BASE-ASSISTANT-CARD-RECTIFY-SAYS-DO-THIS-IN-INVOICING: in Spanish the card said «Hacer esto en Facturación»
// (a closed list of 24 verbs); now it names the action, and so does the receipt. Cancelled: nothing is issued.
test('BASE-F97 — in Spanish the card and the receipt of rectifying say «Rectificar en Facturación», never «Hacer esto»', async ({ browser }) => {
  const FIX = 'FIX-HUB-BASE-ASSISTANT-CARD-RECTIFY-SAYS-DO-THIS-IN-INVOICING';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices');
  // In Spanish (the Hub's language cookie, as the sign-in sets it).
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${A}/invoice/invoices`);
  const invoice = await anInvoice(context);
  await openPanel(page);
  await ask(page, asked(invoice.number));
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await expect(card(page)).toContainText('¿Ejecutar esta acción?');
  await expect(card(page)).not.toContainText('Hacer esto');
  const sentence = card(page).locator('.assistant-confirm-text').first();
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(sentence).toHaveText('Rectificar en Facturación. Revisa cada dato antes de seguir.');
    // The action's name wraps inside the card, never past it (390 wide).
    expect(await sentence.evaluate((el) => el.scrollWidth <= el.clientWidth), `${FIX}-${vp.label} overflows`).toBe(true);
    await untilStill(page);
    await page.screenshot({ path: shot(`${FIX}-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await expect(receipts(page).last()).toHaveText('No se hizo, cancelado: Rectificar en Facturación');
  expect((await invoiceOf(context, invoice.id)).status).toBe('issued');
  await context.close();
});

// FIX-HUB-INVOICE-ASSISTANT-RECTIFY-CARD-WITHOUT-PREVIEW: the card of rectifying listed only what it sends (the number
// and the reason), never the rectifying invoice it issues. Through base's preview (BASE-F98) its «Lo que va a pasar»
// shows the type, the next number of the RECT series (read, never taken) and the base, the tax and the total in
// negative, as money. «Cancelar» issues nothing and takes no number; the word issues exactly the number it said.
test('INVOICE-F08 — in Spanish the rectification card shows what will happen: the type, the next number and the amounts in negative as money', async ({ browser }) => {
  const FIX = 'FIX-HUB-INVOICE-ASSISTANT-RECTIFY-CARD-WITHOUT-PREVIEW';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${A}/invoice/invoices`);
  const invoice = await anInvoice(context);
  const said = (await previewOf(context, invoice.number)).next_number;
  const lines = [
    'Tipo de rectificativa: R1',
    `Siguiente número: ${said}`,
    'Base imponible: -100,00 €',
    'Impuesto: -21,00 €',
    'Total: -121,00 €',
  ];

  await openPanel(page);
  await ask(page, asked(invoice.number));
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await expect(card(page)).toContainText('¿Ejecutar esta acción?');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(previewBlock(page)).toContainText('Lo que va a pasar');
    await expect(previewBlock(page).locator('li')).toHaveText(lines);
    // Each line wraps inside the card, never past it (390 wide).
    expect(await previewBlock(page).evaluate((el) => el.scrollWidth <= el.clientWidth), `${FIX}-${vp.label} overflows`).toBe(true);
    await untilStill(page);
    await page.screenshot({ path: shot(`${FIX}-${vp.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // «Cancelar»: nothing is issued, and the number the card said is still the next one (it was never taken).
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  expect((await invoiceOf(context, invoice.id)).status).toBe('issued');
  expect((await previewOf(context, invoice.number)).next_number).toBe(said);

  // Asked again, the word typed: the rectifying invoice carries exactly the number the card said.
  await ask(page, asked(invoice.number));
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await expect(previewBlock(page).locator('li')).toHaveText(lines);
  await card(page).locator('[data-testid="assistant-confirm-input"] input').fill('CONFIRMAR');
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText('Hecho.');
  const after = await invoiceOf(context, invoice.id);
  expect([after.status, after.rectifications]).toMatchObject(['cancelled', [{ number: said }]]);
  issuedIds.add(after.rectifications[0].id);
  await context.close();
});

// FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: an invoice issued in euros, rectified once
// erplora.com had registered the business in Poland, showed «Total: -121,00 zł» in «What will happen»: the card
// painted every amount in the business's currency. Each amount of the preview is now in the one its read answers (the
// invoice's, which keeps the one it was issued in), in English and in Spanish; «Cancel» issues nothing. Asked first in
// English, the receipt of that turn read in Spanish once the person switched said «Rectificar en Invoicing»: now it is
// said whole in the screen's language, and nothing on the Spanish screen is left in English.
test('BASE-F97 — with the business moved to Poland, the rectification card says the euro invoice’s amounts in euros, never in złoty', async ({ browser }) => {
  const FIX = 'FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY';
  const registration = registrationOf('a');
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/invoice/invoices');
  await page.setViewportSize({ width: 1440, height: 900 });
  // Issued while the business is in Spain: in euros.
  await registerBusinessIn(registration, 'ES');
  const invoice = await anInvoice(context);
  expect(((await invoiceOf(context, invoice.id)) as InvoiceOut & { currency: string }).currency).toBe('EUR');
  await registerBusinessIn(registration, 'PL');
  try {
    // The business now charges in złoty (the card's own currency, for what a write sends).
    const business = await api<{ currency: string }>(context, A, 'GET', '/business');
    expect([business.status, business.data.currency]).toEqual([200, 'PLN']);
    for (const language of ['en', 'es'] as const) {
      await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(`${A}/invoice/invoices`);
      await openPanel(page);
      if (language === 'es') {
        // The receipt of the turn asked in English, read now in Spanish: whole in Spanish, the app by its menu.
        await expect(receipts(page)).toHaveText(['No se hizo, cancelado: Rectificar en Facturación']);
      }
      await ask(page, asked(invoice.number));
      await expect(card(page)).toBeVisible({ timeout: 30_000 });
      const said = (await previewOf(context, invoice.number)).next_number;
      const lines =
        language === 'en'
          ? ['Type of rectifying invoice: R1', `Next number: ${said}`, 'Tax base: -€100.00', 'Tax: -€21.00', 'Total: -€121.00']
          : ['Tipo de rectificativa: R1', `Siguiente número: ${said}`, 'Base imponible: -100,00 €', 'Impuesto: -21,00 €', 'Total: -121,00 €'];
      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await expect(previewBlock(page).locator('li')).toHaveText(lines);
        await expect(previewBlock(page)).not.toContainText('zł');
        if (language === 'es') {
          // Nothing on the Spanish screen in English: neither the card, nor a receipt, nor the panel.
          for (const english of ['Invoicing', 'Not done', 'Rectify in', 'What will happen', 'Run this action', 'Tax base']) {
            await expect(page.locator('body')).not.toContainText(english, { useInnerText: true });
          }
        }
        expect(await previewBlock(page).evaluate((el) => el.scrollWidth <= el.clientWidth), `${FIX}-${language}-${vp.label} overflows`).toBe(true);
        await untilStill(page);
        await page.screenshot({ path: shot(language === 'en' ? `${FIX}-${vp.label}` : `${FIX}-es-${vp.label}`) });
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      // «Cancel»: nothing is issued.
      await decide(page, 'cancel');
      await expect(receipts(page).last()).toHaveText(
        language === 'en' ? 'Not done, cancelled: Rectify in Invoicing' : 'No se hizo, cancelado: Rectificar en Facturación',
      );
      expect((await invoiceOf(context, invoice.id)).status).toBe('issued');
    }
  } finally {
    await registerBusinessIn(registration, registration.country);
    await context.close();
  }
});

test('INVOICE-F08 — asked to rectify a rectifying invoice, the assistant says why and offers no card', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/invoice/invoices');
  const context = page.context();
  const invoice = await anInvoice(context);
  const done = await api<{ invoice: InvoiceOut }>(context, A, 'POST', '/invoice/invoices/rectify', { number: invoice.number, reason: `e2e ${RUN}` });
  expect(done.status, JSON.stringify(done.data)).toBe(200);
  issuedIds.add(done.data.invoice.id);
  const rectifying = done.data.invoice.number;

  await openPanel(page);
  await ask(page, asked(rectifying));
  await expect(lastAnswer(page)).toContainText('No se puede rectificar:');
  await expect(lastAnswer(page)).toContainText('A rectifying invoice cannot be rectified.');
  await expect(card(page)).toBeHidden();
  expect(toldPreview()).toMatchObject({ error: { code: 'invoice.cannot_rectify_rectification' } });
  // Nothing new: the rectifying one is still the only one.
  expect((await invoiceOf(context, invoice.id)).rectifications).toHaveLength(1);
  await untilStill(page);
  await page.screenshot({ path: shot(`${KEY}-refused-1440`) });
});
