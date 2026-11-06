// hub#679: since hub#416 the assistant's card left out every id its schema does not mark, so saving the website from the
// chat said no logo, no cover, no photo of the gallery and no category of the catalog, and the palette, the page's
// background, what the catalog shows and the days of the opening hours went by their codes («ocean», «auto», «service»,
// «mon»). Now each image goes by the name of the file it was uploaded with, each category by its name and each value of
// a closed list by the word the editor shows, read as the person, in their language, never by its id. End to end with
// the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be
// seeded with it (README of this folder, «El asistente»). Cancelled, nothing changes. What this file creates (photos
// `e2e-web-…`, a category «E2E Web …» of Services) goes away (`cleanUp`); the apps it turns on are turned off again.
// flow: WEBSITE-F01 WEBSITE-F02 WEBSITE-F04 WEBSITE-F05 WEBSITE-F11 BASE-F97
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { cancel, cardSpec, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, psql, untilStill } from './helpers';
import { photo, type Site } from './website-helpers';

/** A business is born with every app off; the catalog reads Services' categories. */
const NEEDED = ['service', 'website'];
/** What this file names what it creates: a category by this, a photo's file by `FILE`. */
const TAG = 'E2E Web';
const FILE = 'e2e-web-';

/** The editor's words for what the save sends, by the language of the card. */
const WORDS = {
  es: { palette: 'Océano', mode: 'Automático', source: 'Servicios', days: ['Lunes', 'Domingo'] },
  en: { palette: 'Ocean', mode: 'Auto', source: 'Services', days: ['Monday', 'Sunday'] },
};

function cleanUp(): void {
  psql(`delete from service_category where name like '${TAG}%'; delete from website_image where filename like '${FILE}%'`);
}

cardSpec(NEEDED, cleanUp);

type Upload = { id: string; url: string; filename: string };

/** A photo of its own (its bytes carry `tag`, so no earlier upload is it), uploaded as the editor does. */
async function upload(context: BrowserContext, page: Page, tag: string, name: string, hue: number): Promise<Upload> {
  const filename = `${FILE}${tag}-${name}.jpg`;
  const bytes = await photo(page, `${tag} ${name}`, hue);
  const sent = await api<{ id: string; url: string }>(context, A, 'POST', '/website/images', {
    filename,
    content_type: 'image/jpeg',
    data_base64: bytes.toString('base64'),
  });
  expect(sent.status, JSON.stringify(sent.data)).toBe(201);
  return { id: sent.data.id, url: sent.data.url, filename };
}

type Said = Record<string, Record<string, unknown>>;

for (const language of ['es', 'en'] as const) {
  const words = WORDS[language];

  test(`website-assistant-card — in ${language}, saving the site says each image, category and list by its name, never by its id or code`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);
    const tag = Date.now().toString(36);
    const [logo, cover, room] = [
      await upload(context, page, tag, 'logo', 20),
      await upload(context, page, tag, 'portada', 140),
      await upload(context, page, tag, 'sala', 260),
    ];
    const category = await api<{ id: string; name: string }>(context, A, 'POST', '/service/categories', {
      name: `${TAG} Peluquería ${tag}`,
    });
    expect(category.status, JSON.stringify(category.data)).toBe(201);
    const found = await api<Site>(context, A, 'GET', '/website/site');
    expect(found.status).toBe(200);
    const { content } = found.data;

    // «Pon en la web el logo, la portada y una foto de la sala, el catálogo de peluquería y el horario del lunes»: the
    // whole site, as the assistant sends it after reading it.
    const fields = await fieldsOf(page, 'website__site__save', {
      template: found.data.template,
      theme: { palette: 'ocean', custom: null, mode: 'auto' },
      content: {
        ...content,
        topbar: { ...content.topbar, logo: { id: logo.id, url: logo.url } },
        hero: { ...content.hero, cover: { id: cover.id, url: cover.url } },
        gallery: { ...content.gallery, hidden: false, images: [{ id: room.id, url: room.url }] },
        catalog: { ...content.catalog, hidden: false, source: 'service', category_ids: [category.data.id] },
        contact: {
          ...content.contact,
          hours: [
            { day: 'mon', intervals: [{ opens: '09:00', closes: '14:00' }] },
            { day: 'sun', intervals: [] },
          ],
        },
      },
    });
    const said = Object.fromEntries(fields.map((field) => [field.name, field.value])) as Record<string, Said>;
    expect([said.theme.palette, said.theme.mode]).toEqual([words.palette, words.mode]);
    const site = said.content;
    expect([site.topbar.logo, site.hero.cover]).toEqual([
      { id: logo.filename, url: logo.url },
      { id: cover.filename, url: cover.url },
    ]);
    expect(site.gallery.images).toEqual([{ id: room.filename, url: room.url }]);
    expect([site.catalog.source, site.catalog.category_ids]).toEqual([words.source, [category.data.name]]);
    expect((site.contact.hours as { day: string }[]).map((row) => row.day)).toEqual(words.days);

    // What the person reads, in every size: the photos by their files, the category by its name, the palette, the
    // background and the days by the editor's words.
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      for (const text of [logo.filename, cover.filename, room.filename, category.data.name, words.palette, words.mode, ...words.days]) {
        await expect(card(page)).toContainText(text);
      }
      await untilStill(page);
      await capture(page, `hub-679-website-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    // Cancelled, nothing changed: the site is as it was.
    const after = await api<Site>(context, A, 'GET', '/website/site');
    expect(after.status).toBe(200);
    expect([after.data.theme, after.data.content]).toEqual([found.data.theme, found.data.content]);
    await context.close();
  });
}
