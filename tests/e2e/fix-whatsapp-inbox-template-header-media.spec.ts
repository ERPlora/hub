// flow: WHATSAPP_INBOX-F29 WHATSAPP_INBOX-F33
// A template whose header is a photo, made from Settings in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md, F29): the
// owner of hub `a` chooses «Photo» as the header in «New template», picks the file (kept at once in the business's
// files), writes the text and sends it for review; the run's real erplora.com uploads the file to Meta as the header's
// sample (Meta's Resumable Upload API) and registers the template with it (door 8, its WORKBOOK WHATSAPP-F16), and the
// row goes from «Not sent to Meta» to «In review», naming its photo. Then (F33) Meta approves it (its webhook to
// erplora.com, which hands the verdict to this Hub) and a conversation sends it with «Template»: the photo comes already
// chosen, erplora.com puts it on the number (`/<NUMBER_ID>/media`) and sends the template naming it, and the thread
// names the photo it went with. The sheet and «Send a template» show the photo's thumbnail, loaded from the address the
// Hub gives it under /p/media/ (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-SHEET-SHOWS-NO-HEADER-THUMBNAIL).
// Meta is the run's Graph (whatsapp-graph.ts): `a`'s number is connected first with the code Meta's window gives
// (door 11, as whatsapp-inbox-connect-return.spec.ts does), so the Graph takes the business's permission; the
// `afterAll` puts back erplora.com's seed (its made-up permission) for the specs after this one. The sheet in three
// sizes (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-HEADER-MEDIA-NOW-STORABLE-390|834|1440), the list (…-list-…), «Send a template»
// with its photo (…-send-…) and the conversation with what was sent (…-sent-…). erplora.com forgets the templates made
// here (`erploraForgetsTemplates`) before and after: its copy would come back to the next run as a row without file.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, psql, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { photo } from './website-helpers';
import { BUSINESS_ID, CODE, type GraphThread, HEADER_HANDLE, MEDIA_ID, META_APP, NUMBER_ID, TEMPLATE_ID, UPLOAD_SESSION, WABA_ID } from './whatsapp-graph';
import { cleanUp, e2ePhone, erploraForgetsTemplates, meta, metaGraph, receive, restorePhoto, seedErplora, system } from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

const TASK = 'FIX-HUB-WHATSAPP-INBOX-TEMPLATE-HEADER-MEDIA-NOW-STORABLE';
const TABLE = 'whatsapp-inbox-templates';
const EDITOR = 'whatsapp-inbox-template-editor';
const FILE_NAME = 'e2e-carta-otono.jpg';

let graph: GraphThread;

const MADE_HERE = 'e2e_foto_';

test.beforeAll(async () => {
  erploraForgetsTemplates(MADE_HERE);
  cleanUp();
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  graph = await metaGraph();
  // The number connected with the code Meta's window gives: erplora.com holds the business's permission, which the
  // run's Graph takes (the seed's made-up one it refuses, as Meta does).
  const connected = system<{ connected: boolean }>('whatsapp_inbox.channel.connect', {
    code: CODE,
    event: 'FINISH',
    waba_id: WABA_ID,
    phone_number_id: NUMBER_ID,
    business_id: BUSINESS_ID,
  });
  expect(connected.connected).toBe(true);
  await graph.forget();
});

test.afterAll(() => {
  // erplora.com's seed again: its made-up permission, the one the other specs find Meta refusing.
  erploraForgetsTemplates(MADE_HERE);
  seedErplora();
  cleanUp();
  restorePhoto();
});

const editor = (page: Page) => page.locator(`ion-modal[data-testid=${EDITOR}]`);
const field = (page: Page, name: string) => editor(page).locator(`[data-testid=${EDITOR}-${name}]`);
const rowOf = (page: Page, name: string) => shown(page).locator(`[data-testid=${TABLE}-row]`, { hasText: name });
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');
const sender = (page: Page) => page.locator('ion-modal[data-testid=whatsapp-inbox-template-form]');
/** The width of a photo the browser decoded (0 until then, or if it could not). */
const loadedWidth = (image: Locator) => image.evaluate((img: HTMLImageElement) => (img.complete ? img.naturalWidth : 0));

/** Picks `label` in an `ion-select` of the sheet (its popover). */
async function choose(page: Page, name: string, label: string): Promise<void> {
  await field(page, name).click();
  await page.locator('ion-popover.select-popover ion-radio', { hasText: label }).click();
  await expect(page.locator('ion-popover.select-popover')).toBeHidden();
}

/** The screen in the three sizes (`<name>-390|834|1440`), with `ready` in sight. */
async function shots(page: Page, name: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await settled(page);
    await noHorizontalScroll(page, `${name} ${viewport.label}`);
    await capture(page, `${name}-${viewport.label}`);
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

test('WHATSAPP_INBOX-F29, F33: a template with a photo header is kept with its file, reaches Meta’s review with it and, approved, is sent with it', async ({ page, request }) => {
  const name = `${MADE_HERE}${Date.now().toString(36)}`;
  await login(page, A, '/whatsapp_inbox/settings');
  /** A JPEG as Meta takes it: its bytes say so (the Hub and erplora.com read them, never the name). */
  const PHOTO = await photo(page, 'Carta', 28);
  await shown(page).locator(`[data-testid=${TABLE}-add]`).click();
  await expect(editor(page)).toBeVisible();
  await field(page, 'name').locator('input').fill(name);

  // «Photo»: the header asks for its file, with what Meta takes; nothing goes for review without it.
  await choose(page, 'header-format', 'Photo');
  await expect(field(page, 'header')).toHaveCount(0);
  await expect(field(page, 'header-file-rules')).toContainText('JPEG or PNG, up to 5 MB.');
  await expect(field(page, 'header-file-empty')).toContainText('No file chosen');
  await field(page, 'body').locator('textarea').fill('¡Llega el otoño! Ven a ver la carta nueva.');
  await expect(field(page, 'submit')).toHaveAttribute('aria-disabled', 'true');

  // A file of another type is said under the field and never uploaded.
  await field(page, 'header-file-input').setInputFiles({ name: 'e2e-carta.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\n') });
  await expect(field(page, 'header-file-error')).toContainText('Choose a JPEG or PNG photo.');

  // The photo: kept at once in the business's files, and named in the sheet with its thumbnail.
  const kept = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/templates/samples'));
  await field(page, 'header-file-input').setInputFiles({ name: FILE_NAME, mimeType: 'image/jpeg', buffer: PHOTO });
  const answer = await kept;
  expect(answer.status()).toBe(201);
  const photoUrl = ((await answer.json()) as { url: string }).url;
  await expect(field(page, 'header-file-name')).toContainText(FILE_NAME);
  await expect(field(page, 'header-file-preview-image')).toHaveAttribute('src', photoUrl);
  await expect.poll(() => loadedWidth(field(page, 'header-file-preview-image'))).toBe(600);
  await expect(field(page, 'header-file-error')).toHaveCount(0);
  await expect(field(page, 'submit')).not.toHaveAttribute('aria-disabled', 'true');
  expect(psql(`select header_format || ' ' || content_type || ' ' || size from whatsapp_inbox_templatesample where name = '${FILE_NAME}' order by created_at desc limit 1`)).toBe(
    `IMAGE image/jpeg ${PHOTO.length}`,
  );
  await shots(page, TASK, async (p) => {
    await expect(field(p, 'header-file-name')).toBeVisible();
  });

  // «Send to Meta for review»: the template leaves the Hub, erplora.com uploads its photo to Meta and registers it.
  await field(page, 'submit').click();
  await expect(editor(page)).toBeHidden();
  await expect(rowOf(page, name)).toContainText('In review', { timeout: 30_000 });
  await expect(rowOf(page, name)).toContainText(`Photo: ${FILE_NAME}`);
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await shots(page, `${TASK}-list`, async (p) => {
    // A new size paints the list again (table or cards): scrolled to once the row it ends with is there.
    await expect(async () => {
      await rowOf(p, name).scrollIntoViewIfNeeded({ timeout: 2_000 });
      await expect(rowOf(p, name)).toBeInViewport({ timeout: 1_000 });
    }).toPass();
  });

  // What Meta received: a session on the e2e Meta app for that file, its bytes, and the template with its handle.
  const { calls } = await graph.seen();
  const session = calls.find((call) => call.path === `/${META_APP.id}/uploads`);
  expect(session?.query).toEqual({ file_name: FILE_NAME, file_length: String(PHOTO.length), file_type: 'image/jpeg' });
  expect(calls.find((call) => call.path === `/${UPLOAD_SESSION}`)?.bytes).toBe(PHOTO.length);
  const registered = calls.find((call) => call.method === 'POST' && call.path === `/${WABA_ID}/message_templates`);
  expect((registered?.json as { name?: string; components?: unknown[] })?.name).toBe(name);
  expect((registered?.json as { components: unknown[] }).components[0]).toEqual({
    type: 'HEADER',
    format: 'IMAGE',
    example: { header_handle: [HEADER_HANDLE] },
  });

  // Meta approves it: its webhook to erplora.com, which hands the verdict to this Hub (the row says «Approved»).
  const verdict = {
    object: 'whatsapp_business_account',
    entry: [
      {
        id: WABA_ID,
        time: Math.floor(Date.now() / 1000),
        changes: [
          {
            field: 'message_template_status_update',
            value: { event: 'APPROVED', message_template_id: Number(TEMPLATE_ID), message_template_name: name, message_template_language: 'es', reason: 'NONE' },
          },
        ],
      },
    ],
  };
  expect(await meta(request, JSON.stringify(verdict))).toBe(200);
  await expect(rowOf(page, name)).toContainText('Approved', { timeout: 30_000 });

  // F33: a customer's conversation; «Template» offers it with its photo already chosen, and sends it.
  const phone = e2ePhone();
  receive(phone, 'Hola, ¿qué tenéis de nuevo?', 'e2e. Ana Otoño');
  await page.goto('/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  await shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone }).click();
  await panel(page).locator('[data-testid=whatsapp-inbox-composer-template]').click();
  await expect(sender(page)).toBeVisible();
  await sender(page).locator('ion-radio', { hasText: name }).click();
  await expect(sender(page).locator('[data-testid=whatsapp-inbox-template-file-name]')).toContainText(FILE_NAME);
  await expect(sender(page).locator('[data-testid=whatsapp-inbox-template-file-preview-image]')).toHaveAttribute('src', photoUrl);
  await expect.poll(() => loadedWidth(sender(page).locator('[data-testid=whatsapp-inbox-template-file-preview-image]'))).toBe(600);
  await expect(sender(page).locator('[data-testid=whatsapp-inbox-template-file-rules]')).toContainText('JPEG or PNG, up to 5 MB.');
  await shots(page, `${TASK}-send`, async (p) => {
    await expect(sender(p).locator('[data-testid=whatsapp-inbox-template-file-name]')).toBeVisible();
  });
  await graph.forget();
  await sender(page).locator('[data-testid=whatsapp-inbox-template-form-submit]').click();
  await expect(sender(page)).toBeHidden();

  // erplora.com put the photo on the number and sent the template naming it; the thread names the photo.
  const sent = panel(page).locator('[data-testid=whatsapp-inbox-message][data-side=outbound]', { hasText: name });
  await expect(sent.locator('[data-testid=whatsapp-inbox-message-header-file]')).toHaveText(`Photo · ${FILE_NAME}`);
  await expect(sent.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Sent', { timeout: 30_000 });
  await shots(page, `${TASK}-sent`, async (p) => {
    await expect(panel(p).locator('[data-testid=whatsapp-inbox-message-header-file]').last()).toBeVisible();
  });
  const sending = (await graph.seen()).calls;
  expect(sending.find((call) => call.method === 'POST' && call.path === `/${NUMBER_ID}/media`)?.bytes).toBeGreaterThan(PHOTO.length);
  const message = sending.find((call) => call.method === 'POST' && call.path === `/${NUMBER_ID}/messages`);
  expect((message?.json as { template: { name: string; components: unknown[] } }).template.name).toBe(name);
  expect((message?.json as { template: { components: unknown[] } }).template.components[0]).toEqual({
    type: 'header',
    parameters: [{ type: 'image', image: { id: MEDIA_ID } }],
  });
});
