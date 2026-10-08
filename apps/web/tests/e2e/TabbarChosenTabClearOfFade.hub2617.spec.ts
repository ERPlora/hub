// Regression test for ERPlora/hub#2617 — the footer tab a person chooses sits whole and clear of
// the edge fade, whether it is tapped on the screen or opened by its link.
//
// What it pins: on a 375px phone, Settings left a tab tapped while it peeked under the 36px «there
// is more» fade exactly where the person's swipe had put it: «Datos y copias» in ios at `scrollLeft`
// 137 of 141 and in md at 347 of 351, «Impresión» in md at 58 — the chosen tab with 36px of the
// fade painted over it. Staff, System and the module screens came out clean because their strip is
// `scrollable`, which is what makes Ionic bring the chosen tab into view; Settings' was not, and
// OutfitKit's own reveal only moves a tab that is fully OUT of view. The rule is the one hub#2603 set
// for every footer strip: the chosen tab is kept clear of any edge that still hides tabs, and the
// last one takes the strip to its end.
//
// A bench spec and not a unit test because the defect is where three things leave the strip after a
// tap (the person's swipe, Ionic's scroll to the chosen tab and OutfitKit's reveal) — happy-dom lays
// nothing out and scrolls nothing (the lesson of hub#2040).
import { expect, request as pwRequest, test, type Page } from '../bench-boot';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
/** The phone of the issue. */
const PHONE = { width: 375, height: 667 };
/** OutfitKit's edge fade (`FADE_PX` in `@erplora/outfitkit/tabbar`). */
const FADE_PX = 36;

const SHELL_SCREENS = [
  { path: '/settings', ready: '[data-testid="settings-tabs"]' },
  { path: '/employees', ready: 'ion-footer .ok-tabbar' },
  { path: '/system', ready: 'ion-footer .ok-tabbar' },
] as const;

interface Session {
  token: string;
  user: unknown;
}

let session: Session;

test.beforeAll(async () => {
  const api = await pwRequest.newContext();
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '000000', device_id: 'e2e-browser-device' },
  });
  expect(res.ok(), `PIN login failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  await api.dispose();
  session = { token: body.token, user: body.user };
});

/**
 * The shell pins `mode: 'ios'` (main.ts), so `md` is reached the way the other tab specs do: the
 * one literal is swapped in the module Vite serves. The fetch is retried when the dev server drops
 * the connection under a neighbouring spec's network storm (hub#2614).
 */
async function forceMaterialMode(page: Page): Promise<void> {
  await page.route(/\/src\/main\.ts(\?.*)?$/, async (route) => {
    let res: Awaited<ReturnType<typeof route.fetch>> | null = null;
    for (let attempt = 1; res === null; attempt += 1) {
      try {
        res = await route.fetch();
      } catch (error) {
        if (attempt >= 3) throw error;
      }
    }
    const body = (await res.text()).replace(/mode: (['"])ios\1, swipeBackEnabled/, 'mode: "md", swipeBackEnabled');
    expect(body, 'main.ts still sets the Ionic mode in one literal').toContain('mode: "md", swipeBackEnabled');
    await route.fulfill({ response: res, body });
  });
}

async function signIn(page: Page): Promise<void> {
  await page.setViewportSize(PHONE);
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [session.token, session.user] as const,
  );
}

/** The address each footer tab of the screen leaves in the URL, chosen one by one. */
async function tabAddresses(page: Page, path: string, ready: string): Promise<string[]> {
  await page.goto(path);
  await expect(page.locator(ready).first()).toBeVisible();
  const tabs = page.locator('ion-footer ion-segment:visible ion-segment-button');
  const count = await tabs.count();
  const addresses: string[] = [];
  for (let index = 0; index < count; index += 1) {
    await tabs.nth(index).click();
    await expect(tabs.nth(index)).toHaveClass(/segment-button-checked/);
    addresses.push(page.url());
  }
  return addresses;
}

interface ChosenTab {
  text: string | undefined;
  overflow: string;
  scrollLeft: number;
  maxScroll: number;
  /** Pixels of the chosen tab under the leading fade (or off the strip). */
  underStart: number;
  /** Pixels of the chosen tab under the trailing fade (or off the strip). */
  underEnd: number;
}

async function measureChosenTab(page: Page): Promise<ChosenTab> {
  return page.evaluate((fade) => {
    const strip = Array.from(document.querySelectorAll<HTMLElement>('ion-footer ion-segment')).find(
      (candidate) => candidate.offsetParent !== null,
    );
    if (!strip) throw new Error('no visible footer tab strip');
    const tab = strip.querySelector<HTMLElement>('ion-segment-button.segment-button-checked');
    if (!tab) throw new Error('no chosen tab');
    const box = strip.getBoundingClientRect();
    const tabBox = tab.getBoundingClientRect();
    const overflow = strip.dataset.overflow ?? 'none';
    const fadeStart = overflow === 'start' || overflow === 'both' ? fade : 0;
    const fadeEnd = overflow === 'end' || overflow === 'both' ? fade : 0;
    return {
      text: tab.textContent?.trim(),
      overflow,
      scrollLeft: Math.round(strip.scrollLeft),
      maxScroll: strip.scrollWidth - strip.clientWidth,
      underStart: Math.max(0, Math.round((box.left + fadeStart - tabBox.left) * 100) / 100),
      underEnd: Math.max(0, Math.round((tabBox.right - (box.right - fadeEnd)) * 100) / 100),
    };
  }, FADE_PX);
}

/** Waits until nothing moves the strip any more: Ionic's smooth scroll and the entry hint are done. */
/**
 * Up to one pixel under the fade is the engine's rounding, not a fault: the strip scrolls by whole
 * pixels and the tabs are sized to fractions of one (96.85px), and that pixel is the fade's
 * transparent end.
 */
const SUB_PIXEL = 1;

function underTheFade(chosen: ChosenTab): boolean {
  return chosen.underStart > SUB_PIXEL || chosen.underEnd > SUB_PIXEL;
}

async function stripAtRest(page: Page): Promise<void> {
  // hub#1829's entry hint moves the strip for ~850 ms; Ionic's smooth scroll runs alongside it.
  await page.waitForTimeout(1_600);
  let last = -1;
  await expect
    .poll(
      async () => {
        const now = (await measureChosenTab(page)).scrollLeft;
        const settled = now === last;
        last = now;
        return settled;
      },
      { intervals: [250], timeout: 5_000 },
    )
    .toBe(true);
}

test.describe('hub2617: the chosen footer tab sits whole and clear of the edge fade', () => {
  for (const screen of SHELL_SCREENS) {
    for (const material of [false, true]) {
      test(`hub2617 ${screen.path} ${material ? 'md' : 'ios'} at 375x667`, async ({ page }) => {
        test.setTimeout(120_000);
        if (material) await forceMaterialMode(page);
        await signIn(page);
        const addresses = await tabAddresses(page, screen.path, screen.ready);
        expect(addresses.length, 'the screen has a tab strip').toBeGreaterThan(1);

        const failures: string[] = [];
        // Chosen on the screen: a tap. Playwright first scrolls the tab just into view, as the person's
        // swipe does — a tab can only be tapped once some of it is on the screen.
        const tabs = page.locator('ion-footer ion-segment:visible ion-segment-button');
        for (let index = 0; index < addresses.length; index += 1) {
          await tabs.nth(index).click();
          await stripAtRest(page);
          const chosen = await measureChosenTab(page);
          if (underTheFade(chosen)) failures.push(`tap ${addresses[index]} ${JSON.stringify(chosen)}`);
        }
        for (const address of addresses) {
          // A real entry by link: a fresh document, not a fragment change on the one already open.
          await page.goto('about:blank');
          await page.goto(address);
          await expect(page.locator(screen.ready).first()).toBeVisible();
          await stripAtRest(page);
          const chosen = await measureChosenTab(page);
          if (underTheFade(chosen)) failures.push(`${address} ${JSON.stringify(chosen)}`);
        }
        expect(failures, `chosen tab under the edge fade:\n${failures.join('\n')}`).toEqual([]);
      });
    }
  }
});
