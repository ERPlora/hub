// flow: WHATSAPP_INBOX-F29
// A template whose header is a photo, made from Settings in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md, F29): the
// owner of hub `a` chooses «Photo» as the header in «New template», picks the file (kept at once in the business's
// files), writes the text and sends it for review; the run's real erplora.com uploads the file to Meta as the header's
// sample (Meta's Resumable Upload API) and registers the template with it (door 8, its WORKBOOK WHATSAPP-F16), and the
// row goes from «Not sent to Meta» to «In review», naming its photo and saying it is not sent from the inbox yet.
// Meta is the run's Graph (whatsapp-graph.ts): `a`'s number is connected first with the code Meta's window gives
// (door 11, as whatsapp-inbox-connect-return.spec.ts does), so the Graph takes the business's permission; the
// `afterAll` puts back erplora.com's seed (its made-up permission) for the specs after this one. The sheet in three
// sizes (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-HEADER-MEDIA-NOW-STORABLE-390|834|1440) and the list (…-list-…).
import { expect, type Page, test } from '@playwright/test';

import { A, login, psql, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { BUSINESS_ID, CODE, type GraphThread, HEADER_HANDLE, META_APP, NUMBER_ID, UPLOAD_SESSION, WABA_ID } from './whatsapp-graph';
import { cleanUp, metaGraph, restorePhoto, seedErplora, system } from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

const TASK = 'FIX-HUB-WHATSAPP-INBOX-TEMPLATE-HEADER-MEDIA-NOW-STORABLE';
const TABLE = 'whatsapp-inbox-templates';
const EDITOR = 'whatsapp-inbox-template-editor';
/** A JPEG as Meta takes it: its bytes say so (the Hub and erplora.com read them, never the name). */
const PHOTO = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01]), Buffer.alloc(4096, 7)]);
const FILE_NAME = 'e2e-carta-otono.jpg';

let graph: GraphThread;

test.beforeAll(async () => {
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
  seedErplora();
  cleanUp();
  restorePhoto();
});

const editor = (page: Page) => page.locator(`ion-modal[data-testid=${EDITOR}]`);
const field = (page: Page, name: string) => editor(page).locator(`[data-testid=${EDITOR}-${name}]`);
const rowOf = (page: Page, name: string) => shown(page).locator(`[data-testid=${TABLE}-row]`, { hasText: name });

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
    await page.screenshot({ path: shot(`${name}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

test('WHATSAPP_INBOX-F29: a template with a photo header is kept with its file and reaches Meta’s review with it', async ({ page }) => {
  const name = `e2e_foto_${Date.now().toString(36)}`;
  await login(page, A, '/whatsapp_inbox/settings');
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

  // The photo: kept at once in the business's files, and named in the sheet.
  const kept = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/templates/samples'));
  await field(page, 'header-file-input').setInputFiles({ name: FILE_NAME, mimeType: 'image/jpeg', buffer: PHOTO });
  expect((await kept).status()).toBe(201);
  await expect(field(page, 'header-file-name')).toContainText(FILE_NAME);
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
  await expect(rowOf(page, name)).toContainText("Can't be sent from the inbox yet: its header has a file.");
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
});
