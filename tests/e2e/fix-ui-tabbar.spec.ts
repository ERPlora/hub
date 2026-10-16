// flow: ui:shell — FIX-UI-TABBAR-375: on a phone (360×740, 375×667, 390×844) the section tabbar of an
// app with four or five tabs shows EVERY tab whole, as a bottom navigation bar does (iOS tab bar,
// Material's navigation bar: three to five destinations, all on screen, labels never cut): no tab past
// the edge of the screen, no strip hiding tabs behind a sideways scroll, no tab spilling into the next,
// and no label cut, neither by its own box nor by its tab. Customers has four tabs, Staff (the owner)
// five; both in Spanish, as Ioan sees them, and in English, the source. The screenshots of Customers at
// 375, 390, 834 and 1440 are the evidence for the comparison with the old hub. More tabs than fit (six,
// or a word wider than a fifth of the strip) keep scrolling with the next tab peeking (`tabbar-peek.ts`).
import { type Browser, type BrowserContext, type Page, expect, test } from '@playwright/test';

import { A, login, record, shot, shown, topbarApps } from './helpers';

/** 360: the most common Android width, the one the 64px floor of the tabs is sized for. */
const PHONES = [
  { label: '360', width: 360, height: 740 },
  { label: '375', width: 375, height: 667 },
  { label: '390', width: 390, height: 844 },
];

const PAGES = [
  { app: 'customer', path: '/customer/customers', tabs: 4 },
  { app: 'staff', path: '/staff/members', tabs: 5 },
];

const LOCALES = ['es', 'en'] as const;

/** The owner on `a` in `language`: the Hub's language cookie, as the sign-in sets it from the account. */
async function ownerPage(browser: Browser, language: (typeof LOCALES)[number]): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 375, height: 667 }, locale: language === 'es' ? 'es-ES' : 'en-GB' });
  const page = await context.newPage();
  await login(page, A, PAGES[0].path);
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  return { context, page };
}

/** Opens `path` and waits until its tabbar is painted and laid out (the peek sizes it on the next frame). */
async function openTabbar(page: Page, path: string, tabs: number): Promise<void> {
  await page.goto(`${A}${path}`);
  await topbarApps(page).waitFor({ state: 'visible' });
  await expect(shown(page).locator('ion-footer.section-tabbar ion-segment-button')).toHaveCount(tabs);
  await page.waitForTimeout(600);
}

/** What the visible page's tabbar looks like: the strip, every tab and its label, in viewport pixels. */
async function tabbarGeometry(page: Page) {
  return page.evaluate(() => {
    const view = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden)') as HTMLElement;
    const segment = view.querySelector('ion-footer.section-tabbar ion-segment') as HTMLElement;
    const round = (n: number) => Math.round(n * 10) / 10;
    const tabs = Array.from(segment.querySelectorAll<HTMLElement>('ion-segment-button')).map((tab) => {
      const label = tab.querySelector('ion-label') as HTMLElement;
      const tabBox = tab.getBoundingClientRect();
      const labelBox = label.getBoundingClientRect();
      const style = getComputedStyle(label);
      return {
        text: label.textContent?.trim() ?? '',
        tabLeft: round(tabBox.left),
        tabRight: round(tabBox.right),
        labelLeft: round(labelBox.left),
        labelRight: round(labelBox.right),
        labelTop: round(labelBox.top),
        labelBottom: round(labelBox.bottom),
        tabTop: round(tabBox.top),
        tabBottom: round(tabBox.bottom),
        scrollWidth: label.scrollWidth,
        clientWidth: label.clientWidth,
        scrollHeight: label.scrollHeight,
        clientHeight: label.clientHeight,
        lines: Math.round(labelBox.height / (parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.1)),
        textOverflow: style.textOverflow,
      };
    });
    return {
      windowWidth: window.innerWidth,
      stripScrollWidth: segment.scrollWidth,
      stripClientWidth: segment.clientWidth,
      overflow: segment.dataset.overflow ?? null,
      tabMin: segment.style.getPropertyValue('--ep-tabbar-min'),
      tabs,
    };
  });
}

type TabbarGeometry = Awaited<ReturnType<typeof tabbarGeometry>>;

/** Every tab on screen, the strip hiding nothing, every label whole inside its tab, in two lines at most. */
function expectAllTabsWhole(g: TabbarGeometry, where: string): void {
  const detail = `${where}: ${JSON.stringify(g)}`;
  expect(g.stripScrollWidth, `the strip hides no tab behind a sideways scroll — ${detail}`).toBeLessThanOrEqual(g.stripClientWidth + 1);
  expect(g.overflow, `no edge fade: nothing is hidden — ${detail}`).toBe('none');
  for (const tab of g.tabs) {
    const at = `«${tab.text}» ${detail}`;
    expect(tab.tabLeft, `the tab starts on screen — ${at}`).toBeGreaterThanOrEqual(0);
    expect(tab.tabRight, `the tab ends on screen — ${at}`).toBeLessThanOrEqual(g.windowWidth);
    // `scroll*` and `client*` are integers rounded apart: a 14.3px label reads 15 and 14. Hence the 1px.
    expect(tab.scrollWidth, `the label is not cut sideways — ${at}`).toBeLessThanOrEqual(tab.clientWidth + 1);
    expect(tab.scrollHeight, `the label is not cut below — ${at}`).toBeLessThanOrEqual(tab.clientHeight + 1);
    expect(tab.labelLeft, `the label starts inside its tab — ${at}`).toBeGreaterThanOrEqual(tab.tabLeft - 0.5);
    expect(tab.labelRight, `the label ends inside its tab — ${at}`).toBeLessThanOrEqual(tab.tabRight + 0.5);
    expect(tab.labelBottom, `the label ends above the tab's bottom — ${at}`).toBeLessThanOrEqual(tab.tabBottom + 0.5);
    expect(tab.lines, `the label takes two lines at most — ${at}`).toBeLessThanOrEqual(2);
    expect(tab.textOverflow, `no «…» — ${at}`).not.toBe('ellipsis');
  }
  // Each tab is its own column: none spills over the strip's 4px gap into the next (Ionic's segment
  // button keeps `min-width: 70px`, wider than a fifth of a phone's strip).
  for (const [i, tab] of g.tabs.slice(0, -1).entries()) {
    expect(g.tabs[i + 1].tabLeft - tab.tabRight, `«${tab.text}» keeps the gap to the next tab — ${detail}`).toBeGreaterThanOrEqual(3.5);
  }
  const last = g.tabs[g.tabs.length - 1];
  expect(last.tabRight, `the last tab is inside the screen — ${detail}`).toBeLessThanOrEqual(g.windowWidth);
}

for (const language of LOCALES) {
  test(`ui:shell — every tab of a 4- and a 5-tab tabbar is whole on a phone (360, 375, 390) in «${language}»`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await ownerPage(browser, language);
    const measured: Record<string, TabbarGeometry> = {};
    try {
      for (const phone of PHONES) {
        await page.setViewportSize({ width: phone.width, height: phone.height });
        for (const { app, path, tabs } of PAGES) {
          await openTabbar(page, path, tabs);
          const g = await tabbarGeometry(page);
          const key = `${language}-${app}-${phone.label}`;
          measured[key] = g;
          await page.screenshot({ path: shot(`FIX-UI-TABBAR-375-${key}`) });
          expectAllTabsWhole(g, key);
        }
      }
    } finally {
      record(`FIX-UI-TABBAR-375-${language}`, measured);
      await context.close();
    }
  });
}

test('ui:shell — Customers with its tabbar at 375, 390, 834 and 1440, every tab whole (evidence for the old hub)', async ({ browser }) => {
  test.setTimeout(240_000);
  const { context, page } = await ownerPage(browser, 'es');
  try {
    for (const viewport of [
      { label: '375', width: 375, height: 667 },
      { label: '390', width: 390, height: 844 },
      { label: '834', width: 834, height: 1112 },
      { label: '1440', width: 1440, height: 900 },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await openTabbar(page, PAGES[0].path, PAGES[0].tabs);
      await page.screenshot({ path: shot(`FIX-UI-TABBAR-375-${viewport.label}`) });
      expectAllTabsWhole(await tabbarGeometry(page), `es-customer-${viewport.label}`);
    }
  } finally {
    await context.close();
  }
});
