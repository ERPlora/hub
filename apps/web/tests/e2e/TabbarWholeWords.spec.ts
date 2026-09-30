// Regression test for ERPlora/hub#2414 — a footer tab never splits a word across two lines.
//
// What it pins: a module's footer tabs let their label wrap BETWEEN words («Lista de / espera»),
// but the tab only had the 116px floor to hold it. In Reservations at 375px that leaves
// «Disponibilidad» 87px in `md` (16px of padding a side) and it came out «Disponibilida» / «d». In
// `ios`, the mode the shell ships, the same word fits with under one pixel to spare, so an Android
// phone with its system text a notch larger (the WebView scales text, not boxes) gets
// «Disponibilid» / «ad». The rule the fix keeps: a tab is at least as wide as the longest word of
// its label; the strip scrolls before a word breaks.
//
// A bench spec and not a unit test because the defect is where the engine breaks a line inside a
// box of a given width — happy-dom lays nothing out (the lesson of hub#2040). It installs a tiny
// module whose tabs carry Reservations' Spanish labels through the dev install route, the same way
// `ModuleSettingsNarrowLabel.spec.ts` does.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { expect, request as pwRequest, test, type Page } from '../bench-boot';
import { hidesTabsSilently, type TabbarGeometry } from '../../src/lib/tabbar-peek';
import { VIEWPORTS } from './viewports';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const FIXTURES = join(import.meta.dirname, 'fixtures', 'modules');
const MODULE_ID = 'e2e_tabs';
/** The phone of the issue. */
const PHONE = { width: 375, height: 667 };
/** Android's «large» system text is 115 %: the WebView grows the text, the boxes stay put. */
const ANDROID_LARGE_TEXT = 1.15;

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
  await page.route(/\/modules\/e2e_tabs\//, async (route) => {
    const url = new URL(route.request().url());
    const [, , ...rest] = url.pathname.replace(/^\/modules\//, '/').split('/');
    const file = rest[0] === 'v' ? rest.slice(2) : rest; // drop `/v/<version>` (hub#935)
    const path = join(FIXTURES, MODULE_ID, ...file);
    // Optional assets the fixture does not ship (icons.json, locales) answer what the runtime does.
    if (!existsSync(path)) return route.fulfill({ status: 404, body: '' });
    await route.fulfill({ path });
  });
}

/**
 * The shell pins `mode: 'ios'` (main.ts) and Ionic ignores `?ionic:mode=` over it, so `md` — the
 * mode the fleet's banks also check — is reached the way those banks do: the one literal is
 * swapped in the module Vite serves.
 */
async function forceMaterialMode(page: Page): Promise<void> {
  await page.route(/\/src\/main\.ts(\?.*)?$/, async (route) => {
    const res = await route.fetch();
    // Vite hands the module back with its own quotes («mode: "ios"»), so either kind matches.
    const body = (await res.text()).replace(/mode: (['"])ios\1, swipeBackEnabled/, 'mode: "md", swipeBackEnabled');
    expect(body, 'main.ts still sets the Ionic mode in one literal').toContain('mode: "md", swipeBackEnabled');
    await route.fulfill({ response: res, body });
  });
}

/** Grows every footer tab label by `scale` from the first paint, as Android's system text size does. */
async function scaleTabText(page: Page, scale: number): Promise<void> {
  await page.addInitScript((factor) => {
    const sheet = document.createElement('style');
    // `em` on the label's own size: whatever the mode gives it (13px ios, 14px md), times factor.
    sheet.textContent = `ion-footer ion-segment-button ion-label { font-size: ${factor}em; }`;
    document.addEventListener('DOMContentLoaded', () => document.head.appendChild(sheet));
  }, scale);
}

async function openModule(
  page: Page,
  viewport: { width: number; height: number },
  tab: 'list' | 'availability' = 'availability',
): Promise<void> {
  await page.setViewportSize(viewport);
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user] as const,
  );
  await serveFixtureAssets(page);
  await page.goto(`/m/${MODULE_ID}/${tab}`);
  await expect(page.getByTestId(`e2e-tabs-${tab}`)).toBeVisible();
  await expect(page.locator('ion-footer ion-segment-button')).toHaveCount(3);
  // Ionic hydrates the buttons and the strip is sized on the next frames; hub#1829's entry hint
  // moves the strip for ~850 ms. What is measured is the strip at rest.
  await page.waitForTimeout(1_600);
}

interface TabLabel {
  text: string;
  /** Some word has characters on two different lines. */
  splitWord: boolean;
  /** Distinct lines the label takes. */
  lines: number;
  /**
   * A character is painted over its tab's padding or beyond it: a word wider than the room eats the
   * gap to the next tab before it ever leaves the tab's box.
   */
  spills: boolean;
  tabWidth: number;
  /** Computed `overflow-wrap`: `normal` is what lets the engine NOT break a word by a letter. */
  overflowWrap: string;
}

async function measureLabels(
  page: Page,
): Promise<{ mode: string | null; labels: TabLabel[]; geometry: TabbarGeometry }> {
  return page.evaluate(() => {
    const strip = Array.from(document.querySelectorAll<HTMLElement>('ion-footer ion-segment')).find(
      (candidate) => candidate.offsetParent !== null,
    );
    if (!strip) throw new Error('no visible footer tab strip');
    const tabs = Array.from(strip.querySelectorAll<HTMLElement>('ion-segment-button'));
    const labels = tabs.map((tab) => {
      const label = tab.querySelector('ion-label');
      if (!label) throw new Error('a tab without its label');
      const box = tab.getBoundingClientRect();
      const native = getComputedStyle(tab.shadowRoot?.querySelector('.button-native') ?? tab);
      const left = box.left + parseFloat(native.paddingLeft) + parseFloat(native.borderLeftWidth);
      const right = box.right - parseFloat(native.paddingRight) - parseFloat(native.borderRightWidth);
      const lineTops: number[] = [];
      let previousLine: number | null = null;
      let splitWord = false;
      let spills = false;
      const walker = document.createTreeWalker(label, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
        for (let index = 0; index < node.data.length; index += 1) {
          if (/\s/.test(node.data[index])) {
            previousLine = null;
            continue;
          }
          const range = document.createRange();
          range.setStart(node, index);
          range.setEnd(node, index + 1);
          const rect = range.getClientRects()[0];
          if (!rect) continue;
          const middle = rect.top + rect.height / 2;
          let line = lineTops.findIndex((top) => Math.abs(top - middle) < rect.height / 2);
          if (line < 0) line = lineTops.push(middle) - 1;
          if (previousLine !== null && previousLine !== line) splitWord = true;
          previousLine = line;
          if (rect.left < left - 0.5 || rect.right > right + 0.5) spills = true;
        }
      }
      return {
        text: label.textContent?.trim() ?? '',
        splitWord,
        lines: lineTops.length,
        spills,
        tabWidth: box.width,
        overflowWrap: getComputedStyle(label).overflowWrap,
      };
    });
    return {
      mode: document.documentElement.getAttribute('mode'),
      labels,
      geometry: {
        visibleWidth: strip.clientWidth,
        contentWidth: strip.scrollWidth,
        firstTabLeft: tabs[0].offsetLeft,
        tabWidth: tabs[0].offsetWidth,
        tabPitch: tabs[1].offsetLeft - tabs[0].offsetLeft,
        tabCount: tabs.length,
      },
    };
  });
}

function expectWholeWords(labels: TabLabel[]): void {
  expect(labels.map((label) => label.text)).toEqual(['Reservas', 'Lista de espera', 'Disponibilidad']);
  for (const label of labels) {
    expect(label.splitWord, `«${label.text}» splits a word: ${JSON.stringify(label)}`).toBe(false);
    expect(label.spills, `«${label.text}» is painted over its tab's padding: ${JSON.stringify(label)}`).toBe(false);
    // Ionic's buttons hand their labels `overflow-wrap: break-word`; with it a word the tab cannot
    // hold yet (the frames before the strip is measured) is broken by a letter instead of waiting.
    expect(label.overflowWrap, `«${label.text}» may still be broken by a letter`).toBe('normal');
  }
}

/** The selected tab sits whole inside the visible part of the strip. */
async function expectChosenTabOnScreen(page: Page): Promise<void> {
  const placement = await page.evaluate(() => {
    const strip = Array.from(document.querySelectorAll<HTMLElement>('ion-footer ion-segment')).find(
      (candidate) => candidate.offsetParent !== null,
    );
    const chosen = strip?.querySelector<HTMLElement>('ion-segment-button.segment-button-checked');
    const box = strip?.getBoundingClientRect();
    const tab = chosen?.getBoundingClientRect();
    return {
      chosen: chosen?.textContent?.trim(),
      stripLeft: box?.left ?? Number.NaN,
      stripRight: box?.right ?? Number.NaN,
      tabLeft: tab?.left ?? Number.NaN,
      tabRight: tab?.right ?? Number.NaN,
      scrollLeft: strip?.scrollLeft,
    };
  });
  expect(placement.chosen).toBe('Disponibilidad');
  const context = JSON.stringify(placement);
  expect(placement.tabLeft, `the chosen tab starts off screen: ${context}`).toBeGreaterThanOrEqual(
    placement.stripLeft - 1,
  );
  expect(placement.tabRight, `the chosen tab ends off screen: ${context}`).toBeLessThanOrEqual(
    placement.stripRight + 1,
  );
}

test.describe('a footer tab never splits a word (hub#2414)', () => {
  test('md at 375px: «Disponibilidad» stays one word, as in the issue', async ({ page }) => {
    await forceMaterialMode(page);
    await openModule(page, PHONE);
    const { mode, labels, geometry } = await measureLabels(page);
    expect(mode, 'the bench really paints Material').toBe('md');
    expectWholeWords(labels);
    // Labels still wrap between words: the fix widens the tab, it does not forbid a second line.
    expect(labels.find((label) => label.text === 'Lista de espera')?.lines).toBeLessThanOrEqual(2);
    expect(hidesTabsSilently(geometry), `the strip hides tabs without showing it: ${JSON.stringify(geometry)}`).toBe(
      false,
    );
  });

  test('ios at 375px with Android large text: the shipped mode does not split it either', async ({ page }) => {
    await scaleTabText(page, ANDROID_LARGE_TEXT);
    await openModule(page, PHONE);
    const { mode, labels, geometry } = await measureLabels(page);
    expect(mode).toBe('ios');
    expectWholeWords(labels);
    expect(hidesTabsSilently(geometry), `the strip hides tabs without showing it: ${JSON.stringify(geometry)}`).toBe(
      false,
    );
  });

  test('ios at 375px: the system text growing AFTER the strip is on screen still keeps words whole', async ({
    page,
  }) => {
    // Android applies a new system text size to an open app: the labels grow after the first paint.
    await openModule(page, PHONE);
    await page.evaluate((factor) => {
      const sheet = document.createElement('style');
      sheet.textContent = `ion-footer ion-segment-button ion-label { font-size: ${factor}em; }`;
      document.head.appendChild(sheet);
    }, ANDROID_LARGE_TEXT);
    await page.waitForTimeout(400);
    const { labels } = await measureLabels(page);
    expectWholeWords(labels);
    // The tabs grew under the person's feet: the one they are on is still whole on screen.
    await expectChosenTabOnScreen(page);
  });

  test('ios at 375px: labels widening AFTER the first paint without the strip changing size still fit', async ({
    page,
  }) => {
    // A web font landing late draws wider glyphs on the same line height: the strip keeps its size
    // and only the labels grow, so only watching each label catches it. (A bigger system text also
    // makes the strip taller, which the strip's own observer already sees.)
    await openModule(page, PHONE);
    const heights = await page.evaluate(() => {
      const strip = Array.from(document.querySelectorAll<HTMLElement>('ion-footer ion-segment')).find(
        (candidate) => candidate.offsetParent !== null,
      );
      const before = strip?.getBoundingClientRect().height ?? 0;
      const sheet = document.createElement('style');
      sheet.textContent = 'ion-footer ion-segment-button ion-label { letter-spacing: 0.2em; }';
      document.head.appendChild(sheet);
      // Read in the same frame, before anything answers: the new glyphs alone leave the strip as it was.
      return { before, sameFrame: strip?.getBoundingClientRect().height ?? -1 };
    });
    expect(heights.sameFrame, 'the scenario: the strip itself does not change size').toBe(heights.before);
    await page.waitForTimeout(400);
    const { labels } = await measureLabels(page);
    expectWholeWords(labels);
  });

  // Choosing a tab re-lays its label (the selected one is painted heavier in `ios`), the strip widens
  // its tabs to the new word a frame later, and the scroll Ionic did to bring the tab into view was
  // measured on the old widths: the tab just chosen ended half off the screen.
  for (const { name, material, viewport, scale } of [
    { name: 'ios at 360px', material: false, viewport: { width: 360, height: 640 }, scale: 1 },
    { name: 'ios at 375px with Android large text', material: false, viewport: PHONE, scale: ANDROID_LARGE_TEXT },
    { name: 'md at 375px', material: true, viewport: PHONE, scale: 1 },
  ]) {
    test(`${name}: the tab just chosen from the edge stays whole on screen`, async ({ page }) => {
      if (material) await forceMaterialMode(page);
      if (scale !== 1) await scaleTabText(page, scale);
      await openModule(page, viewport, 'list');
      await page.locator('ion-footer ion-segment-button', { hasText: 'Disponibilidad' }).click();
      await expect(page.getByTestId('e2e-tabs-availability')).toBeVisible();
      await page.waitForTimeout(1_200);
      await expectChosenTabOnScreen(page);
    });
  }

  test('a shell strip whose labels never wrap is not widened to its whole labels', async ({ page }) => {
    // Staff, Settings and System keep Ionic's single-line label, which ends in an ellipsis when it
    // does not fit — the fallback Material and iOS use. Widening their tabs to the WHOLE label is a
    // different decision (every tab of those screens would grow), not this fix.
    await page.setViewportSize(PHONE);
    await page.addInitScript(
      ([token, user]) => {
        localStorage.setItem('erplora.hub_session', token as string);
        localStorage.setItem('erplora.session', JSON.stringify(user));
      },
      [session.token, session.user] as const,
    );
    await page.goto('/employees');
    await expect(page.locator('.ok-tabbar')).toBeVisible();
    await page.waitForTimeout(1_600);
    const tabs = await page.evaluate(() => {
      const strip = Array.from(document.querySelectorAll<HTMLElement>('ion-footer ion-segment')).find(
        (candidate) => candidate.offsetParent !== null,
      );
      return Array.from(strip?.querySelectorAll<HTMLElement>('ion-segment-button') ?? []).map((tab) => {
        const label = tab.querySelector<HTMLElement>('ion-label');
        return {
          whiteSpace: label ? getComputedStyle(label).whiteSpace : '',
          fullLabel: label?.scrollWidth ?? 0,
          room: label?.clientWidth ?? 0,
        };
      });
    });
    expect(tabs.length).toBeGreaterThan(1);
    expect(tabs.every((tab) => tab.whiteSpace === 'nowrap')).toBe(true);
    // The bench has to hold a label longer than its tab («Aprobaciones»), or this proves nothing.
    expect(tabs.some((tab) => tab.fullLabel > tab.room + 1)).toBe(true);
  });

  for (const viewport of VIEWPORTS) {
    for (const material of [false, true]) {
      test(`${material ? 'md' : 'ios'} at ${viewport.width}px: every label reads whole`, async ({ page }) => {
        if (material) await forceMaterialMode(page);
        await openModule(page, viewport);
        const { mode, labels } = await measureLabels(page);
        expect(mode).toBe(material ? 'md' : 'ios');
        expectWholeWords(labels);
      });
    }
  }
});
