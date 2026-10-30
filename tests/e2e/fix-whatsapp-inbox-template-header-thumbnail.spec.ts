// flow: WHATSAPP_INBOX-F29 WHATSAPP_INBOX-F30 WHATSAPP_INBOX-F33
// FIX-HUB-WHATSAPP-INBOX-TEMPLATE-SHEET-SHOWS-NO-HEADER-THUMBNAIL, in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): the
// file of a template's photo, video or document header is shown as WhatsApp Manager, WATI or respond.io show it. In
// «New template» (F29) the photo just chosen shows its thumbnail, loaded from the address the Hub gives it under
// /p/media/ (served to the hub's sessions only, `members_media`); a video, its first frame with a play sign; a document,
// its icon. Saved, «Edit» (F30) shows the template's own photo. In a conversation, «Send a template» (F33) shows the
// thumbnail of the photo chosen now for a template made in WhatsApp Manager; the one made here, which comes with its
// own photo once Meta approves it, is fix-whatsapp-inbox-template-header-media.spec.ts. The sheet in three sizes
// (FIX-HUB-WHATSAPP-INBOX-TEMPLATE-SHEET-SHOWS-NO-HEADER-THUMBNAIL-390|834|1440), «Edit» (…-edit-…) and «Send a
// template» (…-send-…). The channel is pushed as erplora.com pushes it; nothing reaches Meta: what the save hands
// erplora.com is not looked at here (fix-whatsapp-inbox-template-header-media.spec.ts follows it to Meta's review).
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, psql, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, rowAction, settled } from './service-helpers';
import { photo } from './website-helpers';
import { cleanUp, e2ePhone, pushChannel, receive, template } from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

const KEY = 'FIX-HUB-WHATSAPP-INBOX-TEMPLATE-SHEET-SHOWS-NO-HEADER-THUMBNAIL';
const TABLE = 'whatsapp-inbox-templates';
const EDITOR = 'whatsapp-inbox-template-editor';
const BODY = '¡Llega el otoño! Ven a ver la carta nueva.';
/** Made here: its photo is the one the sheet keeps. */
const MADE = `e2e_miniatura_${Date.now().toString(36)}`;
/** Made in WhatsApp Manager with a photo header: «Send a template» asks for its file. */
const MANAGER = template('e2e_miniatura_manager', { header_format: 'IMAGE', body: 'Oferta de otoño', variables: 0 });
/** A 96×72 MP4 (H.264, two frames, `ftyp isom`), as Meta takes a video header. */
const VIDEO = Buffer.from(
  'AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAMIbW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAAZAAAQAAAQAAAAAAAAAAAAAA' +
  'AAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAld0cmFrAAAAXHRraGQAAAAD' +
  'AAAAAAAAAAAAAAABAAAAAAAAAZAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAGAAAABIAAAAAAAk' +
  'ZWR0cwAAABxlbHN0AAAAAAAAAAEAAAGQAAAAAAABAAAAAAHPbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAoAAAAEABVxAAAAAAALWhkbHIAAAAA' +
  'AAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABem1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAA' +
  'AQAAAAx1cmwgAAAAAQAAATpzdGJsAAAAunN0c2QAAAAAAAAAAQAAAKphdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAGAASABIAAAASAAAAAAA' +
  'AAABDExhdmMgbGlieDI2NAAAAAAAAAAAAAAAAAAAAAAAAAAAGP//AAAAMGF2Y0MBQsAK/+EAGGdCwArZBi/lwEQAAAMABAAAAwAoPEiZIAEABWjL' +
  'gJSyAAAAEHBhc3AAAAABAAAAAQAAABRidHJ0AAAAAAAAPuQAAAAAAAAAGHN0dHMAAAAAAAAAAQAAAAIAAAgAAAAAFHN0c3MAAAAAAAAAAQAAAAEA' +
  'AAAcc3RzYwAAAAAAAAABAAAAAQAAAAIAAAABAAAAHHN0c3oAAAAAAAAAAAAAAAIAAAL7AAAAKgAAABRzdGNvAAAAAAAAAAEAAAM4AAAAPXVkdGEA' +
  'AAA1bWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAIaWxzdAAAAAhmcmVlAAADLW1kYXQAAAL3ZYiENwxgAQ9fgzSU' +
  '4AD//8ELtawBIQkNovBa12DwNiATSYZKePcnwkX8bw347gjnOfmEKAwIEAASFG7A2bMm9f4ef4Bvth0ZTvpH3e2BwfjMBwJCAOmCIFBwAgBYDiuI' +
  'gTGDoExGYDgSkAAECBMEQABBLiAB2K4rg6BMQdAmP8/AOCyGfeWA4QkBjBAAEBwkodGQZOPXgR7rG1XxlHAGbt3/4elU+G8UD+AQ+6R9kBgAZggQ' +
  'AmrP4THZsSBsYARwvkgy7/vv+1gtAvCBAA/3XxvMGYP2b69+Og63LngH6XLcVy0ExB0EwZ7qZaeFnN//8AClOI46Nq0uM9pMungDhCRHxDvB0Ful' +
  'PgFOx5IVa+nutsPf8O7HwCN/86v/++Fhf4Sc3/+Aktpc9/enplp4WcAr21T7012uf992avvp9yH4AHKRGUY547gNtWeeGlb/6IEb3CAFkuBKRhAS' +
  'nNybwOmOWOZP///4Aum92e/xQBGH8b+DFMnYAGDfdae+ADnIJfPhIEwKIAAgRBXLECYrankGzliejCtTz/EI/odzZxVXfAoSDAAKgIl6GkF/A5Aw' +
  '0sXL+IYB8cga7QMWy5aC7CB2gYK6DhNFR5Bx+BItHLtKO6GR+/3w/8by4Dey24DZsn8MAAiCsgwkgOiPLB0I/ouygilmZFai74B//H+LXrhzBAGF' +
  'CDojyw6Q5flZyz+lst+DeP/4A26e6e85af1/fhgc8DCGQil+zLxcCM2KSZI5f4ycBwBMcAAQEUwRAAEAKIAAdBcTYibEHgbEHgbFRnD/0Oh1AV8J' +
  'uKIUAfjFPhUABgMEACfhQjC/qrwu3ABirGkiB3fftbDBq7gskBwCYwBUwMALAkMAJmsZO86yzh1AVC7DqAqF2KwMAE4ABkwDBUAAQNQpAIbELEQs' +
  'QdAmIOgTEA5EXjCg5gIs3AR6AhfW3gPnhTAAwECABGWiCSbFZfDAEYNZQzEuSJFciEAD/4K54YoB4TMwOAAIAIj37GfYlwNiPA2MAAAAJkGaOCuE' +
  '1gigp6mzVq9/mX7wxDH6iJLy+HOHOtjXn+Pl1v9RJpPA',
  'base64',
);
const PDF = Buffer.from('%PDF-1.7\n%e2e\n');

test.beforeAll(() => {
  cleanUp();
  pushChannel({ status: 'connected', templates: [MANAGER] });
});

test.afterAll(() => {
  cleanUp();
});

const editor = (page: Page) => page.locator(`ion-modal[data-testid=${EDITOR}]`);
const field = (page: Page, name: string) => editor(page).locator(`[data-testid=${EDITOR}-${name}]`);
const sender = (page: Page) => page.locator('ion-modal[data-testid=whatsapp-inbox-template-form]');
const inSender = (page: Page, name: string) => sender(page).locator(`[data-testid=whatsapp-inbox-template-${name}]`);
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

test('WHATSAPP_INBOX-F29, F30: the template’s sheet shows the thumbnail of its photo, the first frame of its video and a document’s icon', async ({ page }) => {
  await login(page, A, '/whatsapp_inbox/settings');
  const carta = await photo(page, 'Carta', 28);
  await shown(page).locator(`[data-testid=${TABLE}-add]`).click();
  await expect(editor(page)).toBeVisible();
  await field(page, 'name').locator('input').fill(MADE);
  await field(page, 'body').locator('textarea').fill(BODY);

  // A photo: kept at once, and shown from the address the Hub gives it, under the inbox's members' folder.
  await choose(page, 'header-format', 'Photo');
  const kept = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/templates/samples'));
  await field(page, 'header-file-input').setInputFiles({ name: 'e2e-carta.jpg', mimeType: 'image/jpeg', buffer: carta });
  const answer = await kept;
  expect(answer.status()).toBe(201);
  const photoUrl = ((await answer.json()) as { url: string }).url;
  expect(photoUrl).toMatch(/^\/p\/media\/[0-9a-f]{32}\/whatsapp_inbox\/samples\/[0-9a-f]{16}\.jpg$/);
  const thumbnail = field(page, 'header-file-preview-image');
  await expect(thumbnail).toHaveAttribute('src', photoUrl);
  await expect(thumbnail).toHaveAttribute('alt', 'e2e-carta.jpg');
  await expect.poll(() => loadedWidth(thumbnail)).toBe(600);
  await expect(field(page, 'header-file-preview-loading')).toHaveCount(0);
  await expect(field(page, 'header-file-preview-error')).toHaveCount(0);
  await expect(field(page, 'header-file-name')).toContainText('e2e-carta.jpg');
  await shots(page, KEY, async (p) => {
    await expect.poll(() => loadedWidth(field(p, 'header-file-preview-image'))).toBe(600);
  });

  // A video: its first frame with the play sign.
  await choose(page, 'header-format', 'Video');
  await expect(field(page, 'header-file-preview')).toHaveCount(0);
  await field(page, 'header-file-input').setInputFiles({ name: 'e2e-otono.mp4', mimeType: 'video/mp4', buffer: VIDEO });
  const video = field(page, 'header-file-preview-video');
  await expect(video).toHaveAttribute('preload', 'metadata');
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => (v.readyState >= 2 ? v.videoWidth : 0))).toBe(96);
  await expect(field(page, 'header-file-preview-play')).toBeVisible();
  await expect(field(page, 'header-file-preview-error')).toHaveCount(0);
  await capture(page, `${KEY}-video-1280`);

  // A document: its icon, with its name and size.
  await choose(page, 'header-format', 'Document');
  await field(page, 'header-file-input').setInputFiles({ name: 'e2e-carta.pdf', mimeType: 'application/pdf', buffer: PDF });
  await expect(field(page, 'header-file-preview-document')).toBeVisible();
  await expect(field(page, 'header-file-preview').locator('img, video')).toHaveCount(0);
  await expect(field(page, 'header-file-name')).toContainText('e2e-carta.pdf');

  // The photo again (the same file is the same address), and «Send to Meta for review».
  await choose(page, 'header-format', 'Photo');
  await field(page, 'header-file-input').setInputFiles({ name: 'e2e-carta.jpg', mimeType: 'image/jpeg', buffer: carta });
  await expect(thumbnail).toHaveAttribute('src', photoUrl);
  await field(page, 'submit').click();
  await expect(editor(page)).toBeHidden();

  // F30: «Edit» shows the template's own photo.
  const id = psql(`select id from whatsapp_inbox_template where name = '${MADE}' and deleted_at is null`);
  await rowAction(page, TABLE, id, 'edit');
  await expect(editor(page)).toBeVisible();
  await expect(field(page, 'header-file-preview-image')).toHaveAttribute('src', photoUrl);
  await expect.poll(() => loadedWidth(field(page, 'header-file-preview-image'))).toBe(600);
  await expect(field(page, 'header-file-choose')).toContainText('Change file');
  await shots(page, `${KEY}-edit`, async (p) => {
    await expect.poll(() => loadedWidth(field(p, 'header-file-preview-image'))).toBe(600);
  });
  await field(page, 'cancel').click();
  await expect(editor(page)).toBeHidden();
});

test('WHATSAPP_INBOX-F33: «Send a template» shows the thumbnail of the photo chosen for a template made in WhatsApp Manager', async ({ page }) => {
  const phone = e2ePhone();
  receive(phone, 'Hola, ¿qué tenéis de nuevo?', 'e2e. Ana Otoño');
  await login(page, A, '/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  await shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone }).click();
  await shown(page).locator('[data-testid=whatsapp-inbox-detail] [data-testid=whatsapp-inbox-composer-template]').click();
  await expect(sender(page)).toBeVisible();

  // Made in WhatsApp Manager: it asks for its file, and the one chosen shows its thumbnail.
  await sender(page).locator('ion-radio', { hasText: MANAGER.name }).click();
  await expect(inSender(page, 'file-empty')).toContainText('No file chosen');
  const menu = await photo(page, 'Menu', 200);
  const kept = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/templates/samples'));
  await inSender(page, 'file-input').setInputFiles({ name: 'e2e-menu.jpg', mimeType: 'image/jpeg', buffer: menu });
  const answer = await kept;
  expect(answer.status()).toBe(201);
  const chosen = ((await answer.json()) as { url: string }).url;
  const thumbnail = inSender(page, 'file-preview-image');
  await expect(thumbnail).toHaveAttribute('src', chosen);
  await expect(thumbnail).toHaveAttribute('alt', 'e2e-menu.jpg');
  await expect.poll(() => loadedWidth(thumbnail)).toBe(600);
  await expect(inSender(page, 'file-name')).toContainText('e2e-menu.jpg');
  await expect(inSender(page, 'file-preview-error')).toHaveCount(0);
  await shots(page, `${KEY}-send`, async (p) => {
    await expect.poll(() => loadedWidth(inSender(p, 'file-preview-image'))).toBe(600);
  });
  await sender(page).locator('[data-testid=whatsapp-inbox-template-form-cancel]').click();
  await expect(sender(page)).toBeHidden();
});
