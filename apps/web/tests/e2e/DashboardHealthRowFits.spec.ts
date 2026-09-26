// Regression test for ERPlora/hub#2201 — on a phone, Home slid sideways while scrolling down.
//
// The culprit was the health row at the foot of Home (zone 5): «Printer not connected» + its way
// out («Set up printing») + «View system» were laid out on ONE line. At 360 px that line is wider
// than the screen, so «View system» ended ~26 px past the right edge. `ion-content` clips the
// overflow (`overflow-x: hidden`) but a clipped box can still be SCROLLED INTO VIEW: the browser
// (a focus, a find-in-page, a screen reader, or the manual recorder's `scrollIntoViewIfNeeded`)
// slides the whole page left to reveal it, and Home is left shifted with its cards cut off.
//
// The row only exists when a printing module is installed (and WhatsApp when its channel stopped),
// and this bench boots an EMPTY hub. So the three readings the row is built from are answered here
// with every line asking for help, and everything else is the real runtime and the real shell.
// Spanish on purpose: its copy is the longest the row has to hold.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';

// 360 px is the narrowest phone in wide use (and the manual recorder's); 390 px is the project's
// phone viewport (`viewports.ts`).
const PHONE_WIDTHS = [360, 390] as const;

test.use({ locale: 'es-ES' });

/**
 * What the health row has to hold. «printer» is the row of the recording that found the bug (a hub
 * with the printing module and no printer yet: every new hub on day one); «printer + WhatsApp» is
 * the longest row there is, each line with its own button.
 */
const SCENARIOS = [
  { name: 'printer', modules: ['printing'], pills: 1, buttons: 2 },
  { name: 'printer + WhatsApp', modules: ['printing', 'whatsapp_inbox'], pills: 2, buttons: 3 },
] as const;

/** Answers the three readings the health row is built from, with every line asking for help. */
async function withHealthRow(page: Page, modules: readonly string[]): Promise<void> {
  await page.route(/\/api\/modules(\?|$)/, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as { ok: boolean; data?: { id: string }[] };
    const data = (body.data ?? []).filter((m) => !modules.includes(m.id));
    for (const id of modules) data.push({ id, name: id, status: 'active', version: '1.0.0' } as { id: string });
    await route.fulfill({ response, json: { ...body, ok: true, data } });
  });
  // Printing installed, nobody draining the receipt roll → «Printer not connected» + its button.
  await page.route(/\/api\/print\/hosts(\?|$)/, (route) =>
    route.fulfill({ json: { ok: true, hosts: [], coverage: [{ role: 'receipt', waiting: 0, liveHosts: 0 }] } }),
  );
  // A number whose permission lapsed → «WhatsApp stopped» + its button (hub#1629).
  await page.route(/\/api\/hub\/whatsapp\/numbers(\?|$)/, (route) =>
    route.fulfill({
      json: {
        numbers: [
          { phone_number_id: 'e2e-1', display_phone: '+34 600 000 000', is_active: true, needs_reconnect: true },
        ],
      },
    }),
  );
}

test.describe('Home health row on a phone (hub#2201)', () => {
  for (const scenario of SCENARIOS)
    for (const width of PHONE_WIDTHS) {
      test(`${scenario.name}: fits the screen at ${width}px and never slides Home sideways`, async ({ page }) => {
        await page.setViewportSize({ width, height: 640 });
        await withHealthRow(page, scenario.modules);
        await loggedInSession(page);
        await page.goto('/dashboard');

        const row = page.locator('.dash-health');
        await expect(row.locator('.dash-health-pill')).toHaveCount(scenario.pills);
        const systemLink = page.locator('.dash-health > .dash-health-link');
        await expect(systemLink).toBeVisible();

        // Every piece of the row is inside the screen: none is waiting to be scrolled into view.
        const pieces = await row.locator('.dash-health-pill, .dash-health-link').evaluateAll((els) =>
          els.map((el) => {
            const box = el.getBoundingClientRect();
            return {
              text: ((el as HTMLElement & { label?: string }).label ?? el.textContent ?? '').trim(),
              left: Math.round(box.left),
              right: Math.round(box.right),
            };
          }),
        );
        expect(pieces).toHaveLength(scenario.pills + scenario.buttons);
        for (const piece of pieces) {
          expect(piece.left, `«${piece.text}» starts left of the screen`).toBeGreaterThanOrEqual(0);
          expect(piece.right, `«${piece.text}» ends past the right edge`).toBeLessThanOrEqual(width);
        }

        // The symptom itself: bring the last piece of Home into view, the way the browser does on its
        // own, and Home must still be where it was — no sideways slide.
        await systemLink.scrollIntoViewIfNeeded();
        const scroller = await row.evaluate(async (el) => {
          const content = el.closest('ion-content') as
            (HTMLElement & { getScrollElement(): Promise<HTMLElement> }) | null;
          if (!content) return null;
          const inner = await content.getScrollElement();
          return { scrollLeft: inner.scrollLeft, scrollWidth: inner.scrollWidth, clientWidth: inner.clientWidth };
        });
        expect(scroller, 'Home is not inside an ion-content').not.toBeNull();
        expect(scroller!.scrollLeft).toBe(0);
        expect(scroller!.scrollWidth).toBeLessThanOrEqual(scroller!.clientWidth);
      });
    }
});
