// The pages of a hub that does not open — still being prepared (503), gone (410), suspended for an unpaid invoice
// (402) — and the sign-in to start again (403) wear ERPlora's look (FIX-HUB-CSP-WHATSAPP-MEDIA; seen by APP-HUBS-1,
// saas#66: they came out as bare HTML in Times). They are rendered without the request, so with no nonce: base's
// static stylesheet and logo, which the strict CSP lets in from 'self'. Each page in three sizes
// (FIX-HUB-CSP-WHATSAPP-MEDIA-gate-<page>-390|834|1440): its stylesheet applied (the system font, the logo painted),
// nothing scrolling sideways and no CSP violation. The hubs it creates are deleted after the file.
// flow: ninguno — FIX base (páginas de puerta del Hub sin estilos; la vio APP-HUBS-1, saas#66)
import { execFileSync } from 'node:child_process';

import { expect, type Page, type Response, test } from '@playwright/test';

import { A, HUB_DIR, shot } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';

/** The registry's rows of this file's hubs, one per gate (base.registry.refusal). */
const HUBS = {
  preparing: { slug: 'e2egate-preparing', fields: "status='requested'" },
  gone: { slug: 'e2egate-gone', fields: "status='cancelled'" },
  suspended: { slug: 'e2egate-suspended', fields: "status='ready', state={'status': 'suspended'}" },
} as const;

function shell(code: string): void {
  execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', code], { cwd: HUB_DIR, encoding: 'utf8' });
}

const forget = "from base.models import Hub\nHub.objects.filter(slug__startswith='e2egate-').delete()";

test.beforeAll(() => {
  const rows = Object.values(HUBS).map(({ slug, fields }) => `Hub.objects.create(slug='${slug}', ${fields})`);
  shell([forget, ...rows].join('\n'));
});

test.afterAll(() => shell(forget));

interface Look {
  sheet: boolean;
  font: string;
  logo: number;
}

/** Whether the gate's stylesheet applied (one the CSP refused has no rules to read) and its logo painted. */
async function look(page: Page): Promise<Look> {
  return page.evaluate(() => {
    const applied = (sheet: CSSStyleSheet): boolean => {
      try {
        return sheet.cssRules.length > 0;
      } catch {
        return false;
      }
    };
    return {
      sheet: [...document.styleSheets].some((sheet) => (sheet.href ?? '').endsWith('/static/base/gate.css') && applied(sheet)),
      font: getComputedStyle(document.body).fontFamily,
      logo: document.querySelector<HTMLImageElement>('img[src$="/static/base/img/logo.png"]')?.naturalWidth ?? 0,
    };
  });
}

/** The sign-in's return with a state this browser never asked for: the 403 that offers to sign in again. */
async function forgedSignIn(page: Page): Promise<Response | null> {
  await page.setContent(
    `<form method="post" action="${A}/auth/callback"><input name="code" value="x"><input name="state" value="forged"><input name="next" value="/"></form>`,
  );
  const [response] = await Promise.all([
    page.waitForResponse((answer) => answer.url() === `${A}/auth/callback`),
    page.evaluate(() => document.forms[0].submit()),
  ]);
  await page.waitForLoadState('load');
  return response;
}

const PAGES = [
  { name: 'preparing', status: 503, heading: 'Your business is being prepared', open: (page: Page) => page.goto(`${STACK.hub(HUBS.preparing.slug)}/`) },
  { name: 'gone', status: 410, heading: 'This business is no longer available', open: (page: Page) => page.goto(`${STACK.hub(HUBS.gone.slug)}/`) },
  { name: 'suspended', status: 402, heading: 'This business is suspended', open: (page: Page) => page.goto(`${STACK.hub(HUBS.suspended.slug)}/`) },
  { name: 'login-retry', status: 403, heading: 'We could not finish signing you in', open: forgedSignIn },
] as const;

for (const gate of PAGES) {
  test(`the ${gate.name} page wears ERPlora's look under the strict CSP, in three sizes`, async ({ page }) => {
    const refused: string[] = [];
    page.on('console', (message) => {
      if (/content security policy|refused to/i.test(message.text())) refused.push(message.text());
    });
    await page.addInitScript(() => {
      const w = window as unknown as { __csp: string[] };
      w.__csp = [];
      document.addEventListener('securitypolicyviolation', (event) => w.__csp.push(`${event.violatedDirective} ${event.blockedURI}`));
    });

    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      const response = await gate.open(page);
      expect(response?.status()).toBe(gate.status);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(gate.heading);
      await expect.poll(() => look(page)).toEqual({ sheet: true, font: expect.stringMatching(/^system-ui/), logo: 512 });
      await settled(page);
      await noHorizontalScroll(page, `gate ${gate.name} ${viewport.label}`);
      await page.screenshot({ path: shot(`FIX-HUB-CSP-WHATSAPP-MEDIA-gate-${gate.name}-${viewport.label}`), fullPage: true });
      expect(await page.evaluate(() => (window as unknown as { __csp: string[] }).__csp)).toEqual([]);
    }
    expect(refused).toEqual([]);
  });
}
