// flow: WHATSAPP_INBOX-F06
// A photo and a voice note in the thread, in a hidden Chrome, against the run's REAL erplora.com (whatsapp-helpers.ts,
// «The run's real erplora.com»; only Meta is played):
// - a photo erplora.com serves (its own picture, the only bytes it hands out without Meta: its attachments stream
//   from Meta, which refuses the seed's made-up permission) is painted inside its bubble, never wider than it, in
//   three sizes, and opens full size in a new tab;
// - a customer's photo and voice note posted by Meta to erplora.com's webhook reach the thread through erplora.com,
//   as a picture and a player: the browser asks erplora.com for both (the Hub's CSP lets it; a refused request never
//   leaves), erplora.com cannot hand them over here (this run's `a.localhost` and erplora.com's `localhost` are two
//   sites, so its session does not travel and it answers 401, which Chrome's ORB hides from an `<img>` or `<audio>`;
//   on `a.erplora.com` and `erplora.com`, one site, it does), and each bubble says so and keeps «Open the attachment».
// erplora.com hands each of Meta's messages to this Hub within its webhook's request: one this Hub refused fails at
// once saying why (`metaHandsOver`), e.g. an attachment linked on another origin than SAAS_URL's.
// Each screen in three sizes (FIX-HUB-WHATSAPP-INBOX-MEDIA-E2E-NEEDS-SAAS-MEDIA-URL-F06-*). What it creates is named
// `e2e.…` and deleted after the file.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, SAAS, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { cleanUp, e2ePhone, metaGraph, metaHandsOver, metaNow, notice, PREFIX, receive, restorePhoto, seedErplora } from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  // erplora.com's accounts and `a`'s number (a made-up Meta permission), and this Hub takes its photo.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
  cleanUp();
});

test.afterAll(() => {
  cleanUp();
  restorePhoto();
});

const TASK = 'FIX-HUB-WHATSAPP-INBOX-MEDIA-E2E-NEEDS-SAAS-MEDIA-URL';
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');
const rowOf = (page: Page, phone: string) => shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) });
const bubbleWith = (page: Page, testid: string) =>
  panel(page).locator('[data-testid=whatsapp-inbox-message]', { has: page.locator(`[data-testid=${testid}]`) });

/** `inner` is painted and stays within `outer`'s width. */
async function within(inner: Locator, outer: Locator): Promise<boolean> {
  const [a, b] = await Promise.all([inner.boundingBox(), outer.boundingBox()]);
  return !!a && !!b && a.width > 0 && a.height > 0 && a.x >= b.x - 0.5 && a.x + a.width <= b.x + b.width + 0.5;
}

async function shots(page: Page, name: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await settled(page);
    await noHorizontalScroll(page, `${name} ${viewport.label}`);
    await ready(page);
    await page.screenshot({ path: shot(`${TASK}-${name}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

async function openConversation(page: Page, phone: string): Promise<void> {
  await rowOf(page, phone).click();
  await expect(panel(page)).toBeVisible();
}

test('WHATSAPP_INBOX-F06: a photo erplora.com serves is painted inside its bubble and opens full size', async ({ page }) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Carla ${Date.now().toString(36)}`;
  const picture = `${SAAS}/static/public/img/og-image.png`;
  receive(phone, '', name, { type: 'image', media: { url: picture, mime_type: 'image/png', filename: '', caption: 'Así lo quiero' } });
  await login(page, A, '/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  await openConversation(page, phone);

  const photo = panel(page).locator('[data-testid=whatsapp-inbox-message-image]');
  await expect(photo).toHaveAttribute('src', picture);
  await expect(photo).toHaveAttribute('alt', 'Así lo quiero');
  await expect.poll(() => photo.evaluate((img: HTMLImageElement) => (img.complete ? img.naturalWidth : 0))).toBe(1200);
  await expect(panel(page).locator('xpath=.//a[.//img]')).toHaveAttribute('href', picture);
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-message-media-error]')).toHaveCount(0);
  await shots(page, 'F06', async (p) => {
    await photo.scrollIntoViewIfNeeded();
    await expect.poll(() => within(photo, bubbleWith(p, 'whatsapp-inbox-message-image'))).toBe(true);
  });
});

test('WHATSAPP_INBOX-F06: a customer’s photo and voice note come through erplora.com; what it cannot hand over says so', async ({ page }) => {
  const phone = e2ePhone();
  const name = `${PREFIX}Lucía ${Date.now().toString(36)}`;
  // Every request of the page to erplora.com's attachments, and how it ended: its status, or why it failed.
  const asked = new Map<string, string>();
  const media = (url: string) => url.startsWith(`${SAAS}/whatsapp/media/`);
  page.on('request', (request) => media(request.url()) && asked.set(request.url(), 'pending'));
  page.on('response', (response) => media(response.url()) && asked.set(response.url(), String(response.status())));
  page.on('requestfailed', (request) => media(request.url()) && asked.set(request.url(), request.failure()?.errorText ?? 'failed'));
  const violations: string[] = [];
  page.on('console', (message) => {
    if (/content security policy/i.test(message.text()) && message.text().includes('/whatsapp/media/')) violations.push(message.text());
  });
  await login(page, A, '/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));

  // What Meta posts to erplora.com's webhook for a photo and a voice note (Meta's media ids; the bytes stay at Meta).
  const sent = (type: 'image' | 'audio', content: Record<string, unknown>) =>
    notice('messages', {
      contacts: [{ profile: { name }, wa_id: phone.slice(1) }],
      messages: [{ from: phone.slice(1), id: `${PREFIX}wamid.${Date.now()}.${type}`, timestamp: metaNow(), type, [type]: content }],
    });
  // erplora.com takes each and hands it to this Hub at once; a refused one fails here saying why (whatsapp-pushes.ts).
  await metaHandsOver(page.request, sent('image', { id: `${PREFIX}media.photo`, mime_type: 'image/jpeg', sha256: 'e2e', caption: 'La foto del pelo' }));
  await metaHandsOver(page.request, sent('audio', { id: `${PREFIX}media.voice`, mime_type: 'audio/ogg; codecs=opus', sha256: 'e2e', voice: true }));
  await expect(rowOf(page, phone)).toBeVisible({ timeout: 30_000 });
  await openConversation(page, phone);

  const attachments = panel(page).locator('[data-testid=whatsapp-inbox-message-media]');
  await expect(attachments).toHaveCount(2, { timeout: 30_000 });
  const [photo, voice] = [attachments.filter({ hasText: 'Photo' }), attachments.filter({ hasText: 'Voice note' })];
  await expect(photo.locator('[data-testid=whatsapp-inbox-message-media-error]')).toHaveText('The image could not be loaded.');
  await expect(voice.locator('[data-testid=whatsapp-inbox-message-media-error]')).toHaveText('The voice note could not be loaded.');
  for (const one of [photo, voice]) {
    const link = one.locator('a');
    await expect(link).toHaveText('Open the attachment');
    await expect(link).toHaveAttribute('href', new RegExp(`^${SAAS}/whatsapp/media/[0-9a-f-]{36}$`));
    await expect(link).toHaveAttribute('target', '_blank');
  }
  // The picture and the player asked erplora.com for exactly these two, and neither got its bytes.
  const hrefs = [await photo.locator('a').getAttribute('href'), await voice.locator('a').getAttribute('href')];
  await expect.poll(() => [...asked.keys()].sort()).toEqual([...hrefs].sort());
  await expect.poll(() => [...asked.values()].every((end) => end !== 'pending' && !/^[23]\d\d$/.test(end))).toBe(true);
  expect(violations).toEqual([]);
  console.log(`erplora.com's attachments: ${[...asked].map(([url, end]) => `${url} → ${end}`).join(' · ')}`);
  await shots(page, 'F06-unloaded', async () => {
    await expect(voice.locator('[data-testid=whatsapp-inbox-message-media-error]')).toBeVisible();
  });
});
