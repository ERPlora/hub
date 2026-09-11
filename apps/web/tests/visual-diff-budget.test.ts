// Guard for the pixel budget of the shell's visual contract (ERPlora/hub#1823).
//
// ── THE DEFECT THIS PINS ─────────────────────────────────────────────────────────────────────
// The bench compared screenshots with `maxDiffPixelRatio: 0.002` — a budget expressed as a
// FRACTION OF THE SCREEN. At 1440x900 that is 2592 pixels, and a changed label is nowhere near
// that big. Measured on 2026-09-11 against this very bench (local darwin, runtime + Vite of the
// bench, 15 captures): rewriting the sidebar footer version from `v0.0.0-bench` to `v1.1.7` moved
// 106 pixels, and changing a single digit (`v1.1.7` -> `v1.1.8`) moved 33. Both runs came back
// `15 passed`. So the green check that reads as "this screen was reviewed" was only ever
// reviewing geometry, and nobody had been told.
//
// ── WHY AN ABSOLUTE BUDGET IS THE FIX, AND NOT A SMALLER RATIO ───────────────────────────────
// What the budget has to stay under is the size of a GLYPH, and a glyph does not grow when the
// viewport does. A ratio therefore makes the contract weakest exactly where the screen is
// biggest: the same one-digit change is 78x under budget at 1440x900 and still 20x under it at
// 390x844. Sizing the guard in the same unit as the thing it guards — pixels of ink — is what
// makes one number hold at all three widths.
//
// ── WHAT PAID FOR THE NUMBER ─────────────────────────────────────────────────────────────────
// The ratio existed to absorb font antialiasing. Measured, that noise is ZERO: three consecutive
// runs of the whole contract (45 captures) with `maxDiffPixels: 0`, against baselines this same
// machine had just generated, came back with not one differing pixel. That is not luck — hub#1752
// and hub#1812 already froze the clock, pinned the timezone, pinned the reported app version and
// masked the install QR, and CI regenerates its baselines on the same runner image it compares
// them on. The blanket the ratio provided had nothing left to absorb.
//
// ── WHAT THIS CONTRACT DOES *NOT* PROMISE ────────────────────────────────────────────────────
// A change smaller than one character. The budget keeps a small cushion above the measured noise
// so that a stray pixel from a browser bump does not turn fifteen captures red at once — and a
// contract that cries wolf is the one that gets muted, which is the disease hub#1752 was closing.
// Anything from one character upward is caught; below that, the component tests and the i18n
// strings are the contract. That sentence is the honest reading of the green check.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { VIEWPORTS } from './e2e/viewports.ts';
import {
  LEGACY_DIFF_PIXEL_RATIO,
  MEASURED_NOISE_FLOOR_PX,
  SMALLEST_MEASURED_TEXT_CHANGE_PX,
  VISUAL_DIFF_BUDGET_PX,
  VISUAL_SCREENSHOT_OPTIONS,
} from './visual-diff-budget.ts';

/**
 * `source` with its comments removed.
 *
 * The guard below greps the config for a reintroduced ratio, and the config's own comment
 * EXPLAINS the ratio it replaced — so a grep over the raw file fails on the explanation, which is
 * how a guard ends up rewritten to be quieter instead of righter. Same trap `merge-pr.sh` has
 * with a `Closes #N` inside a code fence (pm#253): read code as code.
 */
export function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}

const CONFIG_SOURCE = withoutComments(
  readFileSync(fileURLToPath(new URL('./playwright.config.ts', import.meta.url)), 'utf8'),
);

describe('the visual contract pixel budget (hub#1823)', () => {
  it('REGRESSION: is an ABSOLUTE pixel count, never a fraction of the screen', () => {
    // The whole defect in one assertion: a ratio scales with the screen, the ink of a label does
    // not, so a ratio can never be the unit of this budget no matter how small it is set.
    expect(VISUAL_SCREENSHOT_OPTIONS.maxDiffPixels).toBe(VISUAL_DIFF_BUDGET_PX);
    expect(VISUAL_SCREENSHOT_OPTIONS).not.toHaveProperty('maxDiffPixelRatio');
  });

  it('still disarms what makes a capture move between runs', () => {
    // Dropping either of these is its own flake, and a flaky contract gets muted (hub#1752).
    expect(VISUAL_SCREENSHOT_OPTIONS.animations).toBe('disabled');
    expect(VISUAL_SCREENSHOT_OPTIONS.caret).toBe('hide');
  });

  it('REGRESSION: fits under the smallest text change ever measured on this bench', () => {
    // 33 px is one digit of the sidebar footer at 1440px, measured on 2026-09-11. If the budget
    // ever climbs back over it, a one-character change goes green again and this guard says so.
    expect(VISUAL_DIFF_BUDGET_PX).toBeLessThan(SMALLEST_MEASURED_TEXT_CHANGE_PX);
  });

  it('keeps a cushion above the measured noise, so one stray pixel is not a red suite', () => {
    expect(VISUAL_DIFF_BUDGET_PX).toBeGreaterThan(MEASURED_NOISE_FLOOR_PX);
  });

  it('REGRESSION: the old ratio hid a ONE-CHARACTER change at all three widths', () => {
    // The arithmetic of the defect, kept executable: this is why the old number could not be
    // "just lowered a bit" and stay a ratio.
    for (const { width, height } of VIEWPORTS) {
      const legacyBudget = width * height * LEGACY_DIFF_PIXEL_RATIO;
      expect(
        legacyBudget,
        `at ${width}x${height} the old threshold allowed ${Math.round(legacyBudget)} px`,
      ).toBeGreaterThan(SMALLEST_MEASURED_TEXT_CHANGE_PX);
    }
  });

  it('reads the config as CODE: a ratio named in a comment is not a ratio in force', () => {
    // Without this the guard is unfalsifiable in the wrong direction — it would fail on the very
    // comment that documents the fix, and the cheapest way out would be to delete the comment.
    expect(withoutComments('// maxDiffPixelRatio: 0.002 used to live here\nconst a = 1;')).not.toMatch(
      /maxDiffPixelRatio/,
    );
    expect(withoutComments('/* maxDiffPixelRatio */\ntoHaveScreenshot: { maxDiffPixelRatio: 0.5 },')).toMatch(
      /maxDiffPixelRatio/,
    );
  });

  it('REGRESSION: playwright.config.ts compares with THIS budget and not a ratio of its own', () => {
    // A constant nobody reads is a comment. The config is where the budget takes effect, so the
    // guard checks the config itself — setting the constant and leaving a hardcoded ratio in
    // place is exactly the shape this defect had.
    expect(
      CONFIG_SOURCE.includes('VISUAL_SCREENSHOT_OPTIONS'),
      'playwright.config.ts no longer uses VISUAL_SCREENSHOT_OPTIONS: this file\'s budget would ' +
        'stop applying and the contract would compare with whatever the config says (hub#1823).',
    ).toBe(true);
    expect(
      /maxDiffPixelRatio/.test(CONFIG_SOURCE),
      'playwright.config.ts sets a maxDiffPixelRatio again: a budget expressed as a fraction of ' +
        'the screen cannot see a small text change — that is the defect of hub#1823.',
    ).toBe(false);
  });
});
