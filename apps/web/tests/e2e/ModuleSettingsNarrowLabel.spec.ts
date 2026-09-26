// On a phone, the label of a number or text setting is readable, not squeezed into a sliver (hub#2224).
//
// What it pins: the Settings screen the shell generates for any module (ADR-0082) painted every
// number and text field as an `<ion-input slot="end">`. Ionic gives a label in the default slot
// `width: min-content` and lets the end slot keep its intrinsic width, and a bare input is ~175px
// wide whatever it holds. At 390px that left Inventory's «Low stock threshold» 113px: the label
// broke in two, its help text in eight, and the field showed «10» in the space of a paragraph.
// Every module with a number or text setting got the same screen.
//
// Why this is a bench spec and not a unit test: the defect is layout — widths the real Ionic item
// hands out in a real browser. A test with a simulated Ionic has no widths to measure (the lesson
// of hub#2040), so this installs a tiny module that only declares `settings` through the dev
// install route and measures the screen the shell builds for it, at the three viewports.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { VIEWPORTS } from './viewports';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const FIXTURES = join(import.meta.dirname, 'fixtures', 'modules');
const MODULE_ID = 'e2e_settings';
/** The settings of the fixture painted as an input: one number, one free text. */
const INPUT_KEYS = ['low_stock_threshold', 'receipt_footer'] as const;

interface Session {
  token: string;
  user: unknown;
}

let session: Session;

async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '000000', device_id: 'e2e-browser-device' },
  });
  expect(res.ok(), `PIN login failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  await api.dispose();
  return { token: body.token, user: body.user };
}

async function moduleCall(path: string, data?: unknown): Promise<void> {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}${path}`, {
    headers: { 'X-Hub-Session': session.token },
    data: data ?? {},
  });
  expect(res.ok(), `${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  await api.dispose();
}

test.beforeAll(async () => {
  expect(MODULES_DIR, 'playwright.config.ts exports the bench modules folder').not.toBe('');
  session = await loginByPin();
  cpSync(join(FIXTURES, MODULE_ID), join(MODULES_DIR, MODULE_ID), { recursive: true });
  await moduleCall('/api/modules/install', { dir: join(MODULES_DIR, MODULE_ID) });
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  await moduleCall(`/api/modules/${MODULE_ID}/uninstall`);
  rmSync(join(MODULES_DIR, MODULE_ID), { recursive: true, force: true });
});

/** The runtime serves module assets in production; in this bench Vite does not, so the spec does. */
async function serveFixtureAssets(page: Page): Promise<void> {
  await page.route(/\/modules\/e2e_settings\//, async (route) => {
    const url = new URL(route.request().url());
    const [, , ...rest] = url.pathname.replace(/^\/modules\//, '/').split('/');
    const file = rest[0] === 'v' ? rest.slice(2) : rest; // drop `/v/<version>` (hub#935)
    const path = join(FIXTURES, MODULE_ID, ...file);
    // Optional assets the fixture does not ship (icons.json, locales) answer what the runtime does.
    if (!existsSync(path)) return route.fulfill({ status: 404, body: '' });
    await route.fulfill({ path });
  });
}

interface FieldBox {
  key: string;
  itemWidth: number;
  labelWidth: number;
  headingLines: number;
  labelRight: number;
  controlLeft: number;
  controlRight: number;
  controlWidth: number;
  itemLeft: number;
  itemRight: number;
}

/** Measures, for each input setting, the box its label and its control got inside the item. */
async function measure(page: Page): Promise<FieldBox[]> {
  return page.evaluate((keys) => {
    return keys.map((key) => {
      const control = document.querySelector(`[data-testid="module-settings-field-${key}"]`);
      const item = control?.closest('ion-item');
      const label = item?.querySelector('ion-label');
      const heading = label?.querySelector('h2');
      if (!control || !item || !label || !heading) throw new Error(`setting ${key} is not on screen`);
      const i = item.getBoundingClientRect();
      const c = control.getBoundingClientRect();
      const h = heading.getBoundingClientRect();
      const lineHeight = parseFloat(getComputedStyle(heading).lineHeight) || h.height;
      return {
        key,
        itemWidth: i.width,
        labelWidth: label.getBoundingClientRect().width,
        headingLines: Math.round(h.height / lineHeight),
        labelRight: label.getBoundingClientRect().right,
        controlLeft: c.left,
        controlRight: c.right,
        controlWidth: c.width,
        itemLeft: i.left,
        itemRight: i.right,
      };
    });
  }, INPUT_KEYS as unknown as string[]);
}

test.describe('a number or text setting keeps a readable label at every width (hub#2224)', () => {
  for (const viewport of VIEWPORTS) {
    test(`at ${viewport.width}px the label is not squeezed by its field`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.addInitScript(
        ([token, user]) => {
          localStorage.setItem('erplora.hub_session', token as string);
          localStorage.setItem('erplora.session', JSON.stringify(user));
        },
        [session.token, session.user] as const,
      );
      await serveFixtureAssets(page);
      await page.goto(`/m/${MODULE_ID}/settings`);
      for (const key of INPUT_KEYS) {
        await expect(page.getByTestId(`module-settings-field-${key}`)).toBeVisible();
      }

      for (const box of await measure(page)) {
        // A three-word label fits on one line of a phone: it is only broken when the field starves it.
        expect(box.headingLines, `${box.key}: the label breaks into ${box.headingLines} lines`).toBe(1);
        // The label and its help text own at least half of the row, whichever layout carries them.
        expect(
          box.labelWidth,
          `${box.key}: the label got ${Math.round(box.labelWidth)}px of a ${Math.round(box.itemWidth)}px row`,
        ).toBeGreaterThanOrEqual(box.itemWidth / 2);
        // …and the field is still a usable field, entirely inside its row.
        expect(box.controlWidth, `${box.key}: the field is ${Math.round(box.controlWidth)}px wide`).toBeGreaterThanOrEqual(64);
        expect(box.controlLeft).toBeGreaterThanOrEqual(box.itemLeft);
        expect(box.controlRight).toBeLessThanOrEqual(box.itemRight + 0.5);
        // On a tablet or a desktop the row has room for both: the field sits beside its label
        // instead of stretching a two-digit number across the whole card.
        if (viewport.width >= 834) {
          expect(box.controlLeft, `${box.key}: the field is not beside its label`).toBeGreaterThanOrEqual(box.labelRight);
        }
      }
    });
  }
});
