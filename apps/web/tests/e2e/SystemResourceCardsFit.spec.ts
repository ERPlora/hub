// Regression test for ERPlora/hub#2418 — on a phone, the «Connections» card of System → Resources
// spilled out of its box.
//
// The four resource cards (CPU, Memory, Database, Connections) sat in an Ionic grid of HALF-width
// columns on a phone and QUARTER-width columns from 768 px up. Ionic's breakpoints follow the
// window, not the room the card really gets, and an `ok-resource-usage` panel needs ~260 px for its
// heading («CONEXIONES» + the «Últimas 24 horas» pill) and its gauge + trend side by side:
//   - 375 px: 162 px per card → «Connections» 5 px wider than its box, the pill of CPU and Memory
//     broken into three lines and «No hemos podido leerlo» into four;
//   - 820 px (tablet): ~190 px → the pill wrapped again and the trend chart squeezed to a sliver;
//   - 1024 px (a laptop, with the side menu open): the same ~190 px.
//
// Both states a hub really shows are measured: the one this bench gives on its own (no SaaS behind
// it, so the series is unreadable and each panel says so) and a measured series, answered here.
// Spanish on purpose: it is the longest copy the cards have to hold.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';

test.use({ locale: 'es-ES' });

/**
 * The three sizes of the UI contract, the narrowest phone in wide use and a laptop with the menu,
 * with the cards each one lays side by side: one per row on a phone, 2×2 on a tablet or beside the
 * menu, four across on a wide desktop (the page must not fall back to one long column there).
 */
const SIZES = [
  { width: 360, height: 640, perRow: 1 },
  { width: 375, height: 667, perRow: 1 },
  { width: 820, height: 1180, perRow: 2 },
  { width: 1024, height: 768, perRow: 2 },
  { width: 1440, height: 900, perRow: 4 },
] as const;

/** The narrowest trend chart that still reads as a history, not as a line of pixels. */
const MIN_TREND_PX = 80;

/** A series the SaaS measured, with the connections under pressure (their sentence is the longest). */
function measuredSeries(): unknown {
  const now = Math.floor(Date.now() / 1000);
  const points = (base: number): [number, number][] =>
    Array.from({ length: 24 }, (_, i) => [now - (23 - i) * 3600, base + (i % 5)]);
  return {
    range: '24h',
    step_seconds: 3600,
    generated_at: new Date().toISOString(),
    thresholds: { warning: 70, critical: 80 },
    metrics: {
      cpu: { known: true, unit: '%', current: 12, status: 'ok', points: points(10), message: null },
      ram: { known: true, unit: '%', current: 77, status: 'warning', points: points(72), message: null },
      db_connections: { known: true, unit: '%', current: 120, status: 'critical', points: points(95), message: null },
    },
  };
}

const STATES = [
  { name: 'unreadable series', measured: false },
  { name: 'measured series', measured: true },
] as const;

interface CardReading {
  label: string;
  scrollWidth: number;
  clientWidth: number;
  top: number;
  left: number;
  right: number;
  labelLines: number;
  rangeLines: number;
  unreadableLines: number | null;
  trendWidth: number | null;
}

/** Measures every resource card of the page, reaching into the panel's shadow root. */
async function readCards(page: Page): Promise<CardReading[]> {
  return page.locator('.resources-grid .metric-card').evaluateAll((cards) => {
    const lines = (el: Element | null | undefined): number => {
      if (!el) return 0;
      const range = document.createRange();
      range.selectNodeContents(el);
      return new Set(Array.from(range.getClientRects(), (r) => Math.round(r.top))).size;
    };
    return cards.map((card) => {
      const box = card.getBoundingClientRect();
      const panel = card.querySelector('ok-resource-usage')?.shadowRoot ?? null;
      const trend = panel?.querySelector('.trend') ?? null;
      const label =
        panel?.querySelector('.label')?.textContent ?? card.querySelector('.metric-stat__label')?.textContent ?? '';
      return {
        label: label.trim(),
        scrollWidth: card.scrollWidth,
        clientWidth: card.clientWidth,
        top: Math.round(box.top),
        left: Math.round(box.left),
        right: Math.round(box.right),
        labelLines: panel ? lines(panel.querySelector('.label')) : 1,
        rangeLines: panel ? lines(panel.querySelector('.range')) : 1,
        unreadableLines: panel?.querySelector('.unreadable-text')
          ? lines(panel.querySelector('.unreadable-text'))
          : null,
        trendWidth: trend ? Math.round(trend.getBoundingClientRect().width) : null,
      };
    });
  });
}

test.describe('System → Resources cards fit their box (hub#2418)', () => {
  for (const state of STATES)
    for (const size of SIZES) {
      test(`${state.name}: every card holds its content at ${size.width}x${size.height}`, async ({ page }) => {
        await page.setViewportSize({ width: size.width, height: size.height });
        if (state.measured)
          await page.route(/\/api\/system\/usage-series(\?|$)/, (route) => route.fulfill({ json: measuredSeries() }));
        await loggedInSession(page);
        await page.goto('/system');

        const panels = page.locator('.resources-grid ok-resource-usage');
        await expect(panels).toHaveCount(3);
        // Wait for the panels to paint the state under test, not their first empty frame.
        const painted = state.measured ? '.trend' : '.unreadable-text';
        await expect
          .poll(() =>
            panels.evaluateAll((els, sel) => els.filter((el) => el.shadowRoot?.querySelector(sel)).length, painted),
          )
          .toBe(3);

        const cards = await readCards(page);
        expect(cards.map((c) => c.label)).toHaveLength(4);
        const firstRow = cards.filter((c) => Math.abs(c.top - cards[0].top) <= 1);
        expect(firstRow.length, `cards side by side at ${size.width}px`).toBe(size.perRow);
        for (const card of cards) {
          const who = `«${card.label}» at ${size.width}px`;
          // The symptom of the issue: the content is wider than the card.
          expect(card.scrollWidth, `${who} spills out of its box`).toBeLessThanOrEqual(card.clientWidth);
          expect(card.left, `${who} starts left of the screen`).toBeGreaterThanOrEqual(0);
          expect(card.right, `${who} ends past the right edge`).toBeLessThanOrEqual(size.width);
          // Heading on one line: the name and the period pill, never broken word by word.
          expect(card.labelLines, `${who}: the name wraps`).toBe(1);
          expect(card.rangeLines, `${who}: the period pill wraps`).toBe(1);
          if (card.unreadableLines !== null)
            expect(card.unreadableLines, `${who}: «could not read it» breaks word by word`).toBeLessThanOrEqual(2);
          if (state.measured && card.trendWidth !== null)
            expect(card.trendWidth, `${who}: the trend chart is squeezed`).toBeGreaterThanOrEqual(MIN_TREND_PX);
        }
        if (state.measured)
          expect(
            cards.filter((c) => c.trendWidth !== null),
            'the three panels draw their trend',
          ).toHaveLength(3);
      });
    }
});
