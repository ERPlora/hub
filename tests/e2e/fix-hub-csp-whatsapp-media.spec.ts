// The thread of a WhatsApp conversation may show a photo and play a voice note that erplora.com serves
// (FIX-HUB-CSP-WHATSAPP-MEDIA, asked by WHATSAPP_INBOX-F06): the Hub's CSP lets `img-src` and `media-src` reach
// the SaaS's origin, and only it. With the thread of a customer who sent a photo open, the page loads an image
// and an audio from the SaaS (as the thread shows an attachment inline) and the same from Meta's CDN: Meta's
// are refused, the SaaS's are not. Violations are caught by the `securitypolicyviolation` event and the console
// («… violates the following Content Security Policy directive»). The thread in three sizes
// (FIX-HUB-CSP-WHATSAPP-MEDIA-390|834|1440). What it creates is deleted after the file.
// flow: ninguno — FIX base (CSP del Hub; la pide WHATSAPP_INBOX-F06, de otro carril)
import { expect, type Page, test } from '@playwright/test';

import { A, login, onSaas, SAAS, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { cleanUp, e2ePhone, PREFIX, pushChannel, receive } from './whatsapp-helpers';

test.afterAll(() => cleanUp());

/** Where Meta keeps a customer's media: never reached from the Hub's page. */
const META_CDN = 'https://mmg.whatsapp.net';

interface Violation {
  directive: string;
  blocked: string;
}

/** Loads `url` as the thread would show it (`<img>` or `<audio>`) and waits until the browser is done with it
 *  (loaded, refused or failed: the SaaS answers this test's made-up attachment with an error). */
async function load(page: Page, tag: 'img' | 'audio', url: string): Promise<void> {
  await page.evaluate(
    ({ tag, url }) =>
      new Promise<void>((resolve) => {
        const element = document.createElement(tag);
        element.hidden = true;
        for (const event of ['load', 'loadedmetadata', 'error']) element.addEventListener(event, () => resolve(), { once: true });
        setTimeout(resolve, 5000);
        if (element instanceof HTMLAudioElement) element.preload = 'metadata';
        element.src = url;
        document.body.append(element);
      }),
    { tag, url },
  );
}

test('the thread may show a photo and play a voice note from erplora.com, and from nowhere else', async ({ page }) => {
  // Chrome says «Loading the image '…' violates the following Content Security Policy directive» (older ones,
  // «Refused to load»). The login goes through the SaaS: its console is the SaaS's (`onSaas`).
  const refused: string[] = [];
  page.on('console', (message) => {
    if (!onSaas(page) && /content security policy|refused to load/i.test(message.text())) refused.push(message.text());
  });
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: Violation[] };
    w.__csp = [];
    document.addEventListener('securitypolicyviolation', (event) =>
      w.__csp.push({ directive: event.violatedDirective, blocked: event.blockedURI }),
    );
  });

  const phone = e2ePhone();
  const name = `${PREFIX}Carla ${Date.now().toString(36)}`;
  pushChannel({ status: 'connected' });
  receive(phone, '¿Me dais cita?', name);
  await login(page, A, '/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
  await shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone }).click();
  const photo = `${SAAS}/whatsapp/media/${PREFIX}foto.jpg`;
  receive(phone, '', name, {
    type: 'image',
    media: { url: photo, mime_type: 'image/jpeg', filename: '', caption: 'Así lo quiero' },
  });
  const media = shown(page).locator('[data-testid=whatsapp-inbox-detail] [data-testid=whatsapp-inbox-message-media]');
  await expect(media).toContainText('Así lo quiero');

  await load(page, 'img', photo);
  await load(page, 'audio', `${SAAS}/whatsapp/media/${PREFIX}nota.ogg`);
  await load(page, 'img', `${META_CDN}/v/${PREFIX}foto.jpg`);
  await load(page, 'audio', `${META_CDN}/v/${PREFIX}nota.ogg`);

  const violations = await page.evaluate(() => (window as unknown as { __csp: Violation[] }).__csp);
  expect(violations.filter((v) => v.blocked.startsWith(SAAS))).toEqual([]);
  // A console line names the blocked URL in quotes, then the directive (which carries the SaaS's origin).
  const blocking = (origin: string) => refused.filter((text) => text.includes(`'${origin}/`));
  expect(blocking(SAAS)).toEqual([]);
  // The control catches the positive: anything that is not the SaaS stays refused, picture and sound alike.
  expect(violations.filter((v) => v.blocked.startsWith(META_CDN)).map((v) => v.directive).sort()).toEqual(['img-src', 'media-src']);
  expect(blocking(META_CDN)).toHaveLength(2);

  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(media).toBeVisible();
    await settled(page);
    await noHorizontalScroll(page, `FIX-HUB-CSP-WHATSAPP-MEDIA ${viewport.label}`);
    await page.screenshot({ path: shot(`FIX-HUB-CSP-WHATSAPP-MEDIA-${viewport.label}`) });
  }
});
