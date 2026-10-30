// flow: base-media-app-folders — FIX-HUB-BASE-MEDIA-DOES-NOT-SERVE-WHATSAPP-INBOX-SAMPLES
// `/p/media/` serves the folders each app declares in its LiveAppConfig (base/media.py): the website's images to any
// visitor (`public_media`), the WhatsApp inbox's template files only to the hub's people (`members_media`). The owner
// uploads a cover and a template's photo; a visitor without a session sees the published page with its cover at
// 390, 834 and 1440 px (`.artifacts/FIX-HUB-BASE-MEDIA-DOES-NOT-SERVE-WHATSAPP-INBOX-SAMPLES-<width>.png`) and gets a
// 404 for the template's photo, which the owner's session opens. At the end the site is taken offline again: the
// other specs on hub `a` expect its `/` to jump to the login.
import { createHash } from 'node:crypto';

import { expect, test } from '@playwright/test';

import { A, api, hostPage, settled, shot, turnOn } from './helpers';
import { photo } from './website-helpers';

const KEY = 'FIX-HUB-BASE-MEDIA-DOES-NOT-SERVE-WHATSAPP-INBOX-SAMPLES';
const WIDTHS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

interface Site {
  template: string;
  theme: unknown;
  content: { hero: Record<string, unknown> } & Record<string, unknown>;
}

test.describe.configure({ mode: 'serial' });

test('base-media-app-folders: a visitor sees the website’s cover, and only the hub’s people open a template’s photo', async ({
  browser,
}) => {
  const { context, page } = await hostPage(browser, A, { next: '/website' });
  try {
    await turnOn(context, A, 'website', 'whatsapp_inbox');
    const cover = await photo(page, 'Media', 20);
    const image = await api<{ id: string; url: string }>(context, A, 'POST', '/website/images', {
      filename: 'cover.jpg',
      content_type: 'image/jpeg',
      data_base64: cover.toString('base64'),
    });
    expect(image.status, JSON.stringify(image.data)).toBe(201);
    expect(image.data.url).toMatch(/^\/p\/media\/[0-9a-f]{32}\/website\/img\//);
    const site = await api<Site>(context, A, 'GET', '/website/site');
    expect(site.status).toBe(200);
    const { template, theme, content } = site.data;
    const saved = await api(context, A, 'POST', '/website/site', {
      template,
      theme,
      content: { ...content, hero: { ...content.hero, title: 'Fresh food every day', cover: { id: image.data.id, url: '' } } },
    });
    expect(saved.status, JSON.stringify(saved.data)).toBe(200);
    expect((await api(context, A, 'POST', '/website/site/publish')).status).toBe(200);

    // The template's photo, kept under the inbox's folder by its content (apps/whatsapp_inbox/samples.py).
    const sample = await photo(page, 'Menu', 200);
    const uploaded = await api<{ id: string }>(context, A, 'POST', '/whatsapp_inbox/templates/samples', {
      header_format: 'IMAGE',
      name: 'carta.jpg',
      content_base64: sample.toString('base64'),
    });
    expect(uploaded.status, JSON.stringify(uploaded.data)).toBe(201);
    const hub = image.data.url.split('/')[3];
    const name = `${createHash('sha256').update(sample).digest('hex').slice(0, 16)}.jpg`;
    const sampleUrl = `${A}/p/media/${hub}/whatsapp_inbox/samples/${name}`;
    const opened = await context.request.get(sampleUrl);
    expect([opened.status(), opened.headers()['content-type']]).toEqual([200, 'image/jpeg']);
    expect(Buffer.from(await opened.body()).equals(sample)).toBe(true);

    for (const width of [390, 834, 1440] as const) {
      const visitor = await browser.newContext({ viewport: WIDTHS[width], locale: 'en-GB' });
      try {
        // Without a session the template's photo is a file that does not exist.
        expect((await visitor.request.get(sampleUrl)).status()).toBe(404);
        const view = await visitor.newPage();
        await view.goto(`${A}/`);
        const hero = view.locator('[data-ep-section="hero"] img');
        await expect(hero).toHaveAttribute('src', image.data.url);
        await expect.poll(() => hero.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
        await settled(view);
        await view.screenshot({ path: shot(`${KEY}-${width}`), fullPage: false });
      } finally {
        await visitor.close();
      }
    }
  } finally {
    const offline = await api<{ is_live: boolean }>(context, A, 'POST', '/website/site/unpublish');
    expect(offline.status).toBe(200);
    await context.close();
  }
});
