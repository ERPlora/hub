// hub#693: saving the website from the assistant showed its whole draft as loose values, with a hidden section's yes or
// no saying nothing about its section. Now the card sums up the actual changes: design, theme, sections hidden or shown
// and the names of the other sections whose content changes, in the person's language. End to end with the stack's SaaS
// gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded with it
// (README of this folder, «El asistente»). Cancelled, nothing changes.
// flow: WEBSITE-F01 WEBSITE-F02 WEBSITE-F03 BASE-F97
import { expect, test } from '@playwright/test';

import { cancel, cardSpec, fieldsOf, ownerIn, VIEWPORTS } from './assistant-card-helpers';
import { card, openPanel } from './assistant-real';
import { A, api, capture, untilStill } from './helpers';
import { type Site } from './website-helpers';

cardSpec(['website'], () => undefined);

const EXPECTED = {
  es: 'Diseño: Moderna · Tema: Bosque · Oscuro · Galería: se oculta · Contenido: Cabecera, Contacto',
  en: 'Design: Modern · Theme: Forest · Dark · Gallery: hidden · Content: Header, Contact',
};

for (const language of ['es', 'en'] as const) {
  test(`website-assistant-card — in ${language}, saving the site sums up its changes instead of dumping the whole draft`, async ({ browser }) => {
    const [context, page] = await ownerIn(browser, language);
    await page.setViewportSize({ width: 1440, height: 900 });
    await openPanel(page);
    const found = await api<Site>(context, A, 'GET', '/website/site');
    expect(found.status).toBe(200);
    const before: Pick<Site, 'template' | 'theme' | 'content'> = {
      template: 'classic',
      theme: { palette: 'ocean', custom: null, mode: 'auto' },
      content: { ...found.data.content, gallery: { ...found.data.content.gallery, hidden: false } },
    };
    const saved = await api<Site>(context, A, 'POST', '/website/site', before);
    expect(saved.status, JSON.stringify(saved.data)).toBe(200);

    const title = `E2E title ${language}`;
    const phone = '+34 911 111 111';
    const fields = await fieldsOf(page, 'website__site__save', {
      template: 'modern',
      theme: { palette: 'forest', custom: null, mode: 'dark' },
      content: {
        ...before.content,
        hero: { ...before.content.hero, title },
        gallery: { ...before.content.gallery, hidden: true },
        contact: { ...before.content.contact, phone },
      },
    });
    expect(fields).toHaveLength(1);
    expect(fields[0]).toMatchObject({
      name: 'summary',
      label: language === 'es' ? 'Resumen' : 'Summary',
      kind: 'text',
      value: EXPECTED[language],
    });

    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await expect(card(page)).toContainText(EXPECTED[language]);
      await expect(card(page)).not.toContainText(title);
      await expect(card(page)).not.toContainText(phone);
      await expect(card(page)).not.toContainText(language === 'es' ? ' · Sí ·' : ' · Yes ·');
      await untilStill(page);
      await capture(page, `hub-693-website-${language}-${vp.label}`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await cancel(page);

    const after = await api<Site>(context, A, 'GET', '/website/site');
    expect(after.status).toBe(200);
    expect([after.data.template, after.data.theme, after.data.content]).toEqual([before.template, before.theme, before.content]);
    const restored = await api<Site>(context, A, 'POST', '/website/site', {
      template: found.data.template,
      theme: found.data.theme,
      content: found.data.content,
    });
    expect(restored.status, JSON.stringify(restored.data)).toBe(200);
    await context.close();
  });
}
